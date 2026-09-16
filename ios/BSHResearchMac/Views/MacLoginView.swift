import SwiftUI

/// High-gloss Summit Glass sign-in view for the macOS app.
/// Features the authentic Berkeley Summit House company logo, frosted glass materials,
/// ambient lighting wash, specular highlights, and polished Apple controls.
struct MacLoginView: View {
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.dismiss) private var dismiss
    @Environment(\.colorScheme) private var colorScheme

    @State private var email = ""
    @State private var password = ""
    @State private var isPasswordVisible = false
    @FocusState private var focus: Field?

    private enum Field: Hashable {
        case email
        case password
    }

    private var canCancel: Bool {
        guard let session = store.session else { return false }
        return MacConfig.bypassLogin || !session.isAnonDev
    }

    private var isDark: Bool {
        colorScheme == .dark
    }

    var body: some View {
        VStack(spacing: 20) {
            // Header & Brand Hero
            VStack(spacing: 12) {
                BSHBrandTile(size: 72, cornerRadius: 18)

                VStack(spacing: 4) {
                    Text("BSH Research Center")
                        .font(.system(size: 22, weight: .bold))
                        .foregroundStyle(.primary)

                    Text("Institutional Terminal · Berkeley Summit House")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundStyle(.secondary)
                }

                // Server Scope Pill
                HStack(spacing: 6) {
                    Circle()
                        .fill(Color.green)
                        .frame(width: 6, height: 6)

                    Text(MacConfig.baseURL.host ?? "Local Node")
                        .font(.system(size: 11, weight: .medium, design: .monospaced))
                        .foregroundStyle(.secondary)

                    if let port = MacConfig.baseURL.port {
                        Text(":\(port)")
                            .font(.system(size: 11, weight: .medium, design: .monospaced))
                            .foregroundStyle(.tertiary)
                    }
                }
                .padding(.horizontal, 10)
                .padding(.vertical, 4)
                .background(
                    Capsule()
                        .fill(Color.primary.opacity(isDark ? 0.08 : 0.05))
                        .overlay(
                            Capsule()
                                .strokeBorder(Color.primary.opacity(isDark ? 0.12 : 0.08), lineWidth: 0.5)
                        )
                )
            }

            // Notices & Warnings
            if let notice = store.sessionNotice {
                noticeBanner(notice, icon: "info.circle.fill", color: .accentColor)
            }

            if let storedError = MacConfig.storedBaseURLError {
                noticeBanner(storedError, icon: "exclamationmark.triangle.fill", color: .orange)
            }

            // Form Inputs Card
            VStack(spacing: 12) {
                emailField
                passwordField
            }

            // Auth Error
            if let error = store.authError {
                noticeBanner(error, icon: "exclamationmark.octagon.fill", color: .red)
                    .transition(.opacity.combined(with: .move(edge: .top)))
            }

            // Action Buttons & Controls
            VStack(spacing: 12) {
                submitButton

                HStack {
                    if canCancel {
                        Button("Cancel") {
                            store.authError = nil
                            dismiss()
                        }
                        .font(.system(size: 12, weight: .medium))
                        .foregroundStyle(.secondary)
                        .buttonStyle(.plain)
                        .keyboardShortcut(.cancelAction)
                    }

                    Spacer()

                    if MacConfig.bypassLogin {
                        Button {
                            store.showLoginSheet = false
                        } label: {
                            HStack(spacing: 4) {
                                Text("Continue without signing in")
                                Image(systemName: "chevron.right")
                                    .font(.system(size: 9, weight: .semibold))
                            }
                            .font(.system(size: 11, weight: .medium))
                            .foregroundStyle(.secondary)
                        }
                        .buttonStyle(.plain)
                    }
                }
            }

            // Footer note
            Text("Memos, decisions and pipeline data synchronize with your institutional account.")
                .font(.system(size: 11))
                .foregroundStyle(.tertiary)
                .multilineTextAlignment(.center)
        }
        .padding(.horizontal, 36)
        .padding(.vertical, 28)
        .frame(width: 480, height: 560)
        .background(
            ZStack {
                // Frosted glass material
                Rectangle()
                    .fill(.ultraThinMaterial)

                // Ambient lighting glow circles
                Circle()
                    .fill(Color.accentColor.opacity(isDark ? 0.22 : 0.14))
                    .frame(width: 320, height: 320)
                    .blur(radius: 65)
                    .offset(x: -120, y: -160)

                Circle()
                    .fill(Color(red: 0.45, green: 0.35, blue: 0.95).opacity(isDark ? 0.16 : 0.10))
                    .frame(width: 300, height: 300)
                    .blur(radius: 60)
                    .offset(x: 130, y: 160)

                // Faint rising mountain watermark
                VStack {
                    Spacer()
                    BSHSummitWatermark(width: 520)
                        .offset(y: 30)
                }
            }
            .allowsHitTesting(false)
        )
        .onAppear {
            focus = .email
        }
        .animation(.spring(response: 0.35, dampingFraction: 0.75), value: store.authError)
    }

    // MARK: - Input Fields

    private var emailField: some View {
        HStack(spacing: 10) {
            Image(systemName: "envelope.fill")
                .font(.system(size: 13, weight: .medium))
                .foregroundStyle(focus == .email ? Color.accentColor : Color.secondary.opacity(0.8))
                .frame(width: 18)

            TextField("Institutional Email", text: $email)
                .textFieldStyle(.plain)
                .font(.system(size: 13))
                .textContentType(.username)
                .focused($focus, equals: .email)
                .onSubmit { focus = .password }

            if !email.isEmpty {
                Button {
                    email = ""
                } label: {
                    Image(systemName: "xmark.circle.fill")
                        .font(.system(size: 11))
                        .foregroundStyle(.tertiary)
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 11)
        .background(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .fill(Color.primary.opacity(isDark ? 0.05 : 0.035))
                .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .strokeBorder(
                    focus == .email
                        ? Color.accentColor
                        : Color.primary.opacity(isDark ? 0.12 : 0.08),
                    lineWidth: focus == .email ? 1.5 : 1
                )
                .shadow(
                    color: focus == .email ? Color.accentColor.opacity(0.35) : .clear,
                    radius: 4
                )
        )
    }

    private var passwordField: some View {
        HStack(spacing: 10) {
            Image(systemName: "lock.fill")
                .font(.system(size: 13, weight: .medium))
                .foregroundStyle(focus == .password ? Color.accentColor : Color.secondary.opacity(0.8))
                .frame(width: 18)

            if isPasswordVisible {
                TextField("Password", text: $password)
                    .textFieldStyle(.plain)
                    .font(.system(size: 13))
                    .textContentType(.password)
                    .focused($focus, equals: .password)
                    .onSubmit { submit() }
            } else {
                SecureField("Password", text: $password)
                    .textFieldStyle(.plain)
                    .font(.system(size: 13))
                    .textContentType(.password)
                    .focused($focus, equals: .password)
                    .onSubmit { submit() }
            }

            Button {
                isPasswordVisible.toggle()
            } label: {
                Image(systemName: isPasswordVisible ? "eye.slash.fill" : "eye.fill")
                    .font(.system(size: 12))
                    .foregroundStyle(isPasswordVisible ? Color.accentColor : Color.secondary)
            }
            .buttonStyle(.plain)
            .help(isPasswordVisible ? "Hide password" : "Show password")
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 11)
        .background(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .fill(Color.primary.opacity(isDark ? 0.05 : 0.035))
                .background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 12, style: .continuous))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .strokeBorder(
                    focus == .password
                        ? Color.accentColor
                        : Color.primary.opacity(isDark ? 0.12 : 0.08),
                    lineWidth: focus == .password ? 1.5 : 1
                )
                .shadow(
                    color: focus == .password ? Color.accentColor.opacity(0.35) : .clear,
                    radius: 4
                )
        )
    }

    // MARK: - Submit Button

    private var submitButton: some View {
        let isDisabled = store.signingIn || email.trimmingCharacters(in: .whitespaces).isEmpty || password.isEmpty

        return Button {
            submit()
        } label: {
            HStack(spacing: 8) {
                if store.signingIn {
                    ProgressView()
                        .controlSize(.small)
                        .tint(.white)
                    Text("Authenticating…")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(.white)
                } else {
                    Text("Sign In to Terminal")
                        .font(.system(size: 13, weight: .semibold))
                        .foregroundStyle(.white)
                    Image(systemName: "arrow.right")
                        .font(.system(size: 11, weight: .bold))
                        .foregroundStyle(.white.opacity(0.9))
                }
            }
            .frame(maxWidth: .infinity)
            .frame(height: 38)
            .background(
                RoundedRectangle(cornerRadius: 11, style: .continuous)
                    .fill(
                        LinearGradient(
                            colors: isDisabled
                                ? [Color.accentColor.opacity(0.35), Color.accentColor.opacity(0.25)]
                                : [
                                    Color.accentColor,
                                    Color(red: 0.03, green: 0.44, blue: 0.76)
                                  ],
                            startPoint: .top,
                            endPoint: .bottom
                        )
                    )
            )
            .overlay(
                RoundedRectangle(cornerRadius: 11, style: .continuous)
                    .strokeBorder(
                        LinearGradient(
                            colors: [
                                Color.white.opacity(isDisabled ? 0.15 : 0.45),
                                Color.white.opacity(isDisabled ? 0.04 : 0.10)
                            ],
                            startPoint: .top,
                            endPoint: .bottom
                        ),
                        lineWidth: 1
                    )
            )
            .shadow(
                color: isDisabled ? .clear : Color.accentColor.opacity(0.35),
                radius: 8,
                y: 3
            )
        }
        .buttonStyle(.plain)
        .keyboardShortcut(.defaultAction)
        .disabled(isDisabled)
    }

    // MARK: - Banner Component

    private func noticeBanner(_ text: String, icon: String, color: Color) -> some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: icon)
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(color)
            Text(text)
                .font(.system(size: 12))
                .foregroundStyle(color == .red ? Color.red : .primary)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
        }
        .padding(12)
        .background(
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .fill(color.opacity(0.08))
                .overlay(
                    RoundedRectangle(cornerRadius: 10, style: .continuous)
                        .strokeBorder(color.opacity(0.22), lineWidth: 1)
                )
        )
    }

    private func submit() {
        Task { await store.signIn(email: email, password: password) }
    }
}
