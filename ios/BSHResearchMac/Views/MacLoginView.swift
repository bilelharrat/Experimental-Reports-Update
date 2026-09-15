import SwiftUI

/// Sign-in sheet. Shown automatically when the server answers 401, or from Account › Sign In.
struct MacLoginView: View {
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.dismiss) private var dismiss

    @State private var email = ""
    @State private var password = ""
    @FocusState private var focus: Field?

    private enum Field { case email, password }

    private var canCancel: Bool {
        guard let session = store.session else { return false }
        return MacConfig.bypassLogin || !session.isAnonDev
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            HStack(spacing: 12) {
                Image(systemName: "building.columns.circle.fill")
                    .font(.system(size: 34))
                    .foregroundStyle(Color.accentColor)
                VStack(alignment: .leading, spacing: 2) {
                    Text("Sign in to BSH Research")
                        .font(.title3.weight(.semibold))
                    Text(MacConfig.baseURL.absoluteString)
                        .font(.caption.monospacedDigit())
                        .foregroundStyle(.secondary)
                }
            }

            if let notice = store.sessionNotice {
                Text(notice)
                    .font(.dsSubhead)
                    .fixedSize(horizontal: false, vertical: true)
            }

            if let storedError = MacConfig.storedBaseURLError {
                Text(storedError)
                    .font(.caption)
                    .foregroundStyle(.orange)
                    .fixedSize(horizontal: false, vertical: true)
            }

            Text("Memos, decisions and desk changes are tied to your account. Same email and password as the web portal.")
                .font(.callout)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)

            VStack(spacing: 10) {
                TextField("Email", text: $email)
                    .textFieldStyle(.roundedBorder)
                    .textContentType(.username)
                    .focused($focus, equals: .email)
                    .onSubmit { focus = .password }
                SecureField("Password", text: $password)
                    .textFieldStyle(.roundedBorder)
                    .textContentType(.password)
                    .focused($focus, equals: .password)
                    .onSubmit { submit() }
            }

            if let error = store.authError {
                Label(error, systemImage: "exclamationmark.triangle.fill")
                    .font(.caption)
                    .foregroundStyle(.red)
                    .fixedSize(horizontal: false, vertical: true)
            }

            HStack {
                if canCancel {
                    Button("Cancel") {
                        store.authError = nil
                        dismiss()
                    }
                    .keyboardShortcut(.cancelAction)
                }
                Spacer()
                if store.signingIn {
                    ProgressView().controlSize(.small)
                }
                Button("Sign In") { submit() }
                    .buttonStyle(.borderedProminent)
                    .keyboardShortcut(.defaultAction)
                    .disabled(store.signingIn || email.isEmpty || password.isEmpty)
            }
        }
        .padding(24)
        .frame(width: 420)
        .onAppear { focus = .email }
    }

    private func submit() {
        Task { await store.signIn(email: email, password: password) }
    }
}
