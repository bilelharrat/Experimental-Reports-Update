import SwiftUI

/// Signing in under Bureau: the website's sign-in sheet (`LoginView.vue` as `bureau.css` sets
/// it). One sheet of the page with the house seal in brass on a square of the desk, fields of
/// fresh paper ruled in ink, a brass pill. It has the website's three forms: sign in, ask
/// for an account, and ask for a reset link.
struct MacBureauLoginView: View {
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.dismiss) private var dismiss
    @Environment(\.colorScheme) private var colorScheme
    let canCancel: Bool

    private enum Mode { case signIn, signUp, forgot, pending, resetSent }
    private enum Field: Hashable { case email, password, confirm }

    @State private var mode: Mode = .signIn
    @State private var email = ""
    @State private var password = ""
    @State private var confirm = ""
    @State private var passwordVisible = false
    @State private var requesting = false
    @State private var requestError: String?
    @FocusState private var focus: Field?

    private var ink: MacBureauPageInk { MacBureauPageInk(scheme: colorScheme) }
    private var isForm: Bool { mode == .signIn || mode == .signUp || mode == .forgot }
    private var busy: Bool { requesting || store.signingIn }
    private var error: String? { mode == .signIn ? store.authError : requestError }

    private var canSubmit: Bool {
        let hasEmail = !email.trimmingCharacters(in: .whitespaces).isEmpty
        switch mode {
        case .signIn: return hasEmail && !password.isEmpty && !busy
        case .signUp: return hasEmail && !password.isEmpty && !confirm.isEmpty && !busy
        case .forgot: return hasEmail && !busy
        case .pending, .resetSent: return false
        }
    }

    private var submitLabel: String {
        switch mode {
        case .signUp: return busy ? "Creating account…" : "Create account"
        case .forgot: return busy ? "Sending request…" : "Ask for a reset link"
        default: return busy ? "Authenticating…" : "Sign In to Terminal"
        }
    }

    var body: some View {
        VStack(spacing: 20) {
            header

            if let notice = store.sessionNotice {
                banner(notice, icon: "circle-alert", tint: ink.info)
            }
            if let stored = MacConfig.storedBaseURLError {
                banner(stored, icon: "circle-alert", tint: ink.warningInk)
            }

            if isForm {
                fields
                if let error {
                    banner(error, icon: "circle-alert", tint: nil)
                        .transition(.opacity.combined(with: .move(edge: .top)))
                }
                actions
            } else {
                notice
            }

            Text("Memos, decisions and pipeline data synchronize with your institutional account.")
                .font(BSHType.bureauSans(11))
                .tracking(0.066)
                .foregroundStyle(ink.subtle)
                .multilineTextAlignment(.center)
                .bureauLines(14, size: 11)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(.horizontal, 36)
        .padding(.vertical, 28)
        .frame(width: 480, height: 560)
        .background {
            ZStack(alignment: .bottom) {
                ink.sheet
                // The summit, rising faintly out of the foot of the sheet.
                BSHBrandMark(width: 520, color: colorScheme == .dark ? Color.white.opacity(0.04) : ink.ink(0.04))
                    .mask(LinearGradient(stops: [.init(color: .black, location: 0.25), .init(color: .clear, location: 0.9)], startPoint: .bottom, endPoint: .top))
                    .offset(y: 30)
            }
            .allowsHitTesting(false)
        }
        .onAppear { focus = .email }
        .animation(.spring(response: 0.35, dampingFraction: 0.75), value: error)
    }

    // MARK: Header

    private var header: some View {
        VStack(spacing: 12) {
            seal
            VStack(spacing: 4) {
                Text("BSH Research Center")
                    .font(.custom(BSHType.bureauSerif, size: 34))
                    .tracking(-0.34)
                    .foregroundStyle(ink.ink)
                    .bureauLines(38, size: 34, em: 1.30)
                Text("Institutional Terminal · Berkeley Summit House")
                    .font(BSHType.bureauSans(12, weight: .medium))
                    .foregroundStyle(ink.secondary)
                    .bureauLines(14, size: 12)
            }
            HStack(spacing: 6) {
                Circle().fill(Color.bshFixed(BSHRGB(52, 199, 89))).frame(width: 6, height: 6)
                Text(MacConfig.baseURL.host ?? "Local Node")
                    .foregroundStyle(ink.secondary)
                if let port = MacConfig.baseURL.port {
                    Text(verbatim: ":\(port)").foregroundStyle(ink.subtle)
                }
            }
            // Chrome resolves the website's mono stack to Menlo (it can't use SF Mono), which
            // has no medium weight.
            .font(.custom("Menlo-Regular", size: 11))
            .frame(height: 13)
            .padding(.horizontal, 10)
            .padding(.vertical, 4)
            .background(Capsule().fill(ink.tray))
            .overlay(Capsule().strokeBorder(ink.ink(0.06), lineWidth: 1))
        }
    }

    /// `.login-tile`: the summit in brass on a square of the desk, lit and grained as the desk is.
    /// On Onyx's white desk by day it is ringed in ink and barely lifted; on a dark desk, lit
    /// along its top and set in a deeper shadow.
    private var seal: some View {
        let desk = MacBureauInk(scheme: colorScheme)
        let light = desk.lightDesk
        let tile = RoundedRectangle(cornerRadius: 18, style: .circular)
        return ZStack {
            MacBureauDesk()
                .environment(\.bureauInk, desk)
            BSHBrandMark(width: 38, color: .bshFixed(light ? MacBureau.brassDeep : MacBureau.brass))
        }
        .frame(width: 72, height: 72)
        .clipShape(tile)
        .overlay {
            if light {
                tile.inset(by: -0.5).stroke(Color.black.opacity(0.1), lineWidth: 1)
            } else {
                tile.inset(by: 0.5)
                    .stroke(LinearGradient(stops: [.init(color: .white.opacity(0.08), location: 0), .init(color: .clear, location: 0.02)], startPoint: .top, endPoint: .bottom), lineWidth: 1)
            }
        }
        // `0 8px 20px -12px` by day, `0 10px 24px -12px` by night: a shadow drawn 12pt
        // inside the tile, dropped and blurred.
        .background {
            tile.inset(by: 12)
                .fill(Color.black.opacity(light ? 0.28 : 0.6))
                .blur(radius: light ? 10 : 12)
                .offset(y: light ? 8 : 10)
        }
    }

    // MARK: Form

    private var fields: some View {
        VStack(spacing: 12) {
            field(.email, icon: "mail") {
                TextField("", text: $email, prompt: Text("Institutional Email").foregroundStyle(ink.subtle))
                    .textContentType(.username)
                    .onSubmit { focus = mode == .forgot ? nil : .password; if mode == .forgot { submit() } }
            } trailing: {
                if !email.isEmpty {
                    Button { email = "" } label: {
                        LucideIcon("x", size: 11).foregroundStyle(ink.subtle)
                    }
                    .buttonStyle(.plain)
                    .help("Clear email")
                }
            }

            if mode != .forgot {
                field(.password, icon: "lock") {
                    Group {
                        if passwordVisible {
                            TextField("", text: $password, prompt: Text("Password").foregroundStyle(ink.subtle))
                        } else {
                            SecureField("", text: $password, prompt: Text("Password").foregroundStyle(ink.subtle))
                        }
                    }
                    .textContentType(mode == .signUp ? .newPassword : .password)
                    .onSubmit { if mode == .signUp { focus = .confirm } else { submit() } }
                } trailing: {
                    Button { passwordVisible.toggle() } label: {
                        LucideIcon(passwordVisible ? "eye-off" : "eye", size: 12)
                            .foregroundStyle(focus == .password || focus == .confirm ? ink.accentInk : ink.secondary)
                    }
                    .buttonStyle(.plain)
                    .help(passwordVisible ? "Hide password" : "Show password")
                }
            }

            if mode == .signUp {
                field(.confirm, icon: "lock") {
                    Group {
                        if passwordVisible {
                            TextField("", text: $confirm, prompt: Text("Confirm password").foregroundStyle(ink.subtle))
                        } else {
                            SecureField("", text: $confirm, prompt: Text("Confirm password").foregroundStyle(ink.subtle))
                        }
                    }
                    .textContentType(.newPassword)
                    .onSubmit { submit() }
                } trailing: { EmptyView() }
            }

            if mode == .forgot {
                Text("There is no automated email here. Asking will flag your account so an administrator can send you a reset link.")
                    .font(BSHType.bureauSans(12))
                    .foregroundStyle(ink.subtle)
                    .bureauLines(16, size: 12)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
    }

    /// `.login-field`: 38pt of fresh paper ruled in ink; in use, a brass edge and its glow.
    private func field<Input: View, Trailing: View>(
        _ which: Field,
        icon: String,
        @ViewBuilder input: () -> Input,
        @ViewBuilder trailing: () -> Trailing
    ) -> some View {
        let focused = focus == which
        let inputView = input()
        let trailingView = trailing()
        return MacBureauLoginField(focused: focused, ink: ink) {
            HStack(spacing: 0) {
                LucideIcon(icon, size: 16)
                    .foregroundStyle(focused ? ink.accentInk : ink.secondary.opacity(0.8))
                    .frame(width: 18)
                inputView
                    .textFieldStyle(.plain)
                    .font(BSHType.bureauSans(13))
                    .foregroundStyle(ink.ink)
                    .focused($focus, equals: which)
                    .disabled(busy)
                    .bureauLines(16, size: 13)
                    .padding(.leading, 10)
                trailingView
            }
        }
    }

    private var actions: some View {
        VStack(spacing: 12) {
            Button(action: submit) {
                HStack(spacing: 8) {
                    if busy {
                        ProgressView().controlSize(.small).tint(.white)
                    }
                    Text(submitLabel)
                        .font(BSHType.bureauSans(13, weight: .semibold))
                    if !busy {
                        LucideIcon("arrow-right", size: 12).opacity(0.9)
                    }
                }
                .foregroundStyle(.white)
                .frame(maxWidth: .infinity)
                .frame(height: 38)
                .background { submitFace }
                .contentShape(Capsule())
            }
            // Waiting, the pill is half-strength brass (`.login-submit:disabled`), with no
            // further dimming of its label.
            .buttonStyle(MacBureauLoginSubmitStyle())
            .keyboardShortcut(.defaultAction)
            .disabled(!canSubmit)

            HStack {
                if mode == .forgot {
                    link("Back to sign in", size: 11) { switchMode(.signIn) }
                } else {
                    link("Forgot password?", size: 11) { switchMode(.forgot) }
                }
                Spacer()
                if mode != .forgot {
                    link(mode == .signUp ? "Already have an account?" : "Need an account?", size: 11, chevron: true) {
                        switchMode(mode == .signUp ? .signIn : .signUp)
                    }
                }
            }

            if canCancel || MacConfig.bypassLogin {
                HStack {
                    if canCancel {
                        link("Cancel", size: 12) {
                            store.authError = nil
                            dismiss()
                        }
                        .keyboardShortcut(.cancelAction)
                    }
                    Spacer()
                    if MacConfig.bypassLogin {
                        link("Continue without signing in", size: 11, chevron: true) {
                            store.showLoginSheet = false
                        }
                    }
                }
            }
        }
    }

    /// `.login-submit`: the brass pill; waiting, brass at half strength.
    @ViewBuilder
    private var submitFace: some View {
        if canSubmit || busy {
            Capsule()
                .fill(ink.accent)
                .overlay(Capsule().fill(LinearGradient(stops: [.init(color: .white.opacity(0.16), location: 0), .init(color: .white.opacity(0), location: 0.6)], startPoint: .top, endPoint: .bottom)))
                .overlay(
                    ZStack {
                        Capsule().fill(Color.white.opacity(0.22))
                        Capsule().fill(Color.black).offset(y: 1).blendMode(.destinationOut)
                    }
                    .compositingGroup()
                    .clipShape(Capsule())
                )
                .background(Capsule().inset(by: -0.5).stroke(ink.accentHover.opacity(0.55), lineWidth: 1))
                .shadow(color: ink.shadow(0.5 * 0.5), radius: 5, y: 6)
        } else {
            Capsule().fill(ink.accent.opacity(0.45))
        }
    }

    private func link(_ title: String, size: CGFloat, chevron: Bool = false, action: @escaping () -> Void) -> some View {
        MacBureauLoginLink(title: title, size: size, chevron: chevron, ink: ink, action: action)
    }

    // MARK: Notices

    /// Request received, or reset asked for: the same sheet, one message and a way back.
    private var notice: some View {
        VStack(spacing: 12) {
            Text(mode == .pending ? "Request received" : "Request sent")
                .font(BSHType.bureauSans(15, weight: .semibold))
                .foregroundStyle(ink.ink)
            Text(mode == .pending
                 ? "An administrator reviews new accounts before they can be used. You will be able to sign in once yours is approved."
                 : "If that address has an account, an administrator has been asked to send you a reset link.")
                .font(BSHType.bureauSans(12))
                .foregroundStyle(ink.secondary)
                .multilineTextAlignment(.center)
                .bureauLines(17, size: 12)
                .fixedSize(horizontal: false, vertical: true)
            link("Back to sign in", size: 12) { switchMode(.signIn) }
        }
        .frame(maxWidth: .infinity)
    }

    /// A notice or an error in its own band; an error is set in the danger ink.
    private func banner(_ text: String, icon: String, tint: Color?) -> some View {
        let red = colorScheme == .dark ? BSHRGB(248, 113, 113) : BSHRGB(220, 38, 38)
        let color = tint ?? .bshFixed(red)
        let edge: Color = tint?.opacity(0.22) ?? .bshFixed(BSHRGB(239, 68, 68), opacity: 0.22)
        let fill: Color = tint?.opacity(0.08) ?? .bshFixed(BSHRGB(239, 68, 68), opacity: 0.08)
        return HStack(alignment: .top, spacing: 10) {
            LucideIcon(icon, size: 13)
                .padding(.top, 1.5)
            Text(text)
                .font(BSHType.bureauSans(12))
                .bureauLines(16, size: 12)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
        }
        .foregroundStyle(color)
        .padding(12)
        .background(RoundedRectangle(cornerRadius: 10, style: .circular).fill(fill))
        .overlay(RoundedRectangle(cornerRadius: 10, style: .circular).strokeBorder(edge, lineWidth: 1))
    }

    // MARK: Acting

    private func switchMode(_ next: Mode) {
        requestError = nil
        store.authError = nil
        password = ""
        confirm = ""
        withAnimation(.easeInOut(duration: 0.18)) { mode = next }
        focus = .email
    }

    private func submit() {
        guard canSubmit else { return }
        let trimmed = email.trimmingCharacters(in: .whitespacesAndNewlines)
        switch mode {
        case .signIn:
            Task { await store.signIn(email: trimmed, password: password) }
        case .signUp:
            guard password == confirm else {
                requestError = "Those passwords do not match."
                return
            }
            requesting = true
            requestError = nil
            Task {
                defer { requesting = false }
                do {
                    try await MacAPIClient.shared.register(email: trimmed, password: password)
                    password = ""
                    confirm = ""
                    mode = .pending
                } catch {
                    requestError = (error as? LocalizedError)?.errorDescription ?? "Couldn't sign in. Try again."
                }
            }
        case .forgot:
            requesting = true
            requestError = nil
            Task {
                defer { requesting = false }
                do {
                    try await MacAPIClient.shared.requestPasswordReset(email: trimmed)
                    mode = .resetSent
                } catch {
                    requestError = (error as? LocalizedError)?.errorDescription ?? "Couldn't sign in. Try again."
                }
            }
        case .pending, .resetSent:
            break
        }
    }
}

/// `.login-field`'s paper: ruled in ink, the rule darker under the pointer; in use, brass
/// with a glow around it.
private struct MacBureauLoginField<Content: View>: View {
    let focused: Bool
    let ink: MacBureauPageInk
    @ViewBuilder let content: () -> Content
    @State private var hovered = false

    var body: some View {
        content()
            .padding(.horizontal, 14)
            .padding(.vertical, 11)
            .background(RoundedRectangle(cornerRadius: 12, style: .circular).fill(ink.raised))
            .overlay(
                RoundedRectangle(cornerRadius: 12, style: .circular)
                    .strokeBorder(focused ? ink.accent : ink.ink(hovered ? 0.28 : 0.14), lineWidth: 1)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 12, style: .circular)
                    .inset(by: -2)
                    .stroke(focused ? ink.accentGlow(0.28) : .clear, lineWidth: 3)
                    .padding(-0.5)
                    .allowsHitTesting(false)
            )
            .onHover { hovered = $0 }
    }
}

/// The sheet's quiet links: medium weight in the secondary ink, in ink under the pointer.
private struct MacBureauLoginLink: View {
    let title: String
    let size: CGFloat
    let chevron: Bool
    let ink: MacBureauPageInk
    let action: () -> Void
    @State private var hovered = false

    var body: some View {
        Button(action: action) {
            HStack(spacing: 4) {
                // The sheet's body leading (1.5) sets these lines' height.
                Text(title)
                    .font(BSHType.bureauSans(size, weight: .medium))
                    .bureauLines(size * 1.5, size: size)
                if chevron {
                    LucideIcon("chevron-right", size: 9)
                }
            }
            .foregroundStyle(hovered ? ink.ink : ink.secondary)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .onHover { hovered = $0 }
    }
}

/// The submit pill's button: its label as drawn, whether or not it can be pressed.
private struct MacBureauLoginSubmitStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .brightness(configuration.isPressed ? -0.05 : 0)
    }
}
