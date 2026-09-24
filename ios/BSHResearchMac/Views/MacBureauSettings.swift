//
//  MacBureauSettings.swift
//  BSHResearchMac
//
//  Settings under Bureau, laid out as the website's Settings page (SettingsView.vue): the
//  title, the profile, then Preferences beside Notifications, Reports beside System, Usage,
//  the fund return policy, Advanced tools, the market desk backup and Operations, from the
//  same endpoints. What only the Mac has (its server, sign-in, token, desk sync, the MCP
//  connector and the thesis) follows in trays of its own.
//

import AppKit
import SwiftUI
import UniformTypeIdentifiers

/// The app's appearance, kept as the website keeps it (`bsh.research.appearance`): Auto
/// follows the system.
enum MacAppearance: String, CaseIterable {
    case auto, light, dark

    static let storageKey = "bsh.research.appearance"

    static var stored: MacAppearance {
        UserDefaults.standard.string(forKey: storageKey).flatMap(MacAppearance.init(rawValue:)) ?? .auto
    }

    var title: String {
        switch self {
        case .auto: return "Auto"
        case .light: return "Light"
        case .dark: return "Dark"
        }
    }

    var icon: String {
        switch self {
        case .auto: return "sun-moon"
        case .light: return "sun"
        case .dark: return "moon"
        }
    }

    /// Applies it to every window.
    func apply() {
        switch self {
        case .auto: NSApplication.shared.appearance = nil
        case .light: NSApplication.shared.appearance = NSAppearance(named: .aqua)
        case .dark: NSApplication.shared.appearance = NSAppearance(named: .darkAqua)
        }
    }
}

struct MacBureauSettingsView: View {
    @EnvironmentObject private var store: MacAppStore
    @EnvironmentObject private var design: BSHDesignStore
    @Environment(\.colorScheme) private var colorScheme

    @State private var settings: MacWorkspaceSettings?
    @State private var profile: MacUserCenter?
    @State private var loading = true
    @State private var loadError: String?
    @State private var saving: String?
    @State private var memoTemplateNotSaved = false
    @State private var appearance = MacAppearance.stored
    @State private var systemDetailsOpen = false
    @State private var sessionsNotice: String?
    @State private var operationsMessage: String?
    @State private var operationsError: String?
    @State private var regenerating = false
    @State private var refreshingStockViews = false
    @State private var deskBusy = false
    @State private var deskMessage: String?
    @State private var deskError: String?
    @State private var confirmingRegen = false
    @State private var confirmingStockViews = false

    private var ink: MacBureauPageInk { MacBureauPageInk(scheme: colorScheme) }

    private var prefs: MacWorkspaceSettings.Preferences? { settings?.preferences }
    private var account: MacWorkspaceSettings.Account? { profile?.account ?? settings?.account }
    private var permissions: [String] { account?.permissions ?? [] }
    private var signedIn: Bool {
        guard let session = store.session else { return false }
        return !session.isAnonDev
    }
    /// With nobody signed in the server fills the email with a placeholder; say what this
    /// Mac is using instead, as the website does.
    private var accountEmail: String {
        signedIn ? (account?.email ?? "") : "Local development"
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                MacBureauPageHeader("Settings")
                    .padding(.bottom, 24)

                if loading && settings == nil && profile == nil {
                    Text("Loading settings…")
                        .font(BSHType.bureauSans(14))
                        .foregroundStyle(ink.muted)
                        .bureauTray()
                } else if let loadError, settings == nil && profile == nil {
                    Text(loadError)
                        .font(BSHType.bureauSans(14))
                        .foregroundStyle(ink.dangerInk)
                        .padding(20)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .background(RoundedRectangle(cornerRadius: 14, style: .circular).fill(ink.dangerSoft))
                } else {
                    content
                }
            }
            .padding(.horizontal, 32)
            .padding(.top, 16)
            .padding(.bottom, 48)
            .frame(maxWidth: 1024)
            .frame(maxWidth: .infinity)
        }
        .background(ink.sheet)
        .task { await load() }
        .confirmationDialog("Regenerate every company?", isPresented: $confirmingRegen) {
            Button("Regenerate all") { Task { await regenerateAll() } }
        } message: {
            Text("This runs a research pass for every company and spends model tokens.")
        }
        .confirmationDialog("Refresh every stock view?", isPresented: $confirmingStockViews) {
            Button("Refresh stock views") { Task { await refreshStockViews() } }
        } message: {
            Text("This refreshes every listed company's stock view and spends model tokens.")
        }
    }

    private var content: some View {
        VStack(alignment: .leading, spacing: 16) {
            profileTray

            Grid(alignment: .topLeading, horizontalSpacing: 16, verticalSpacing: 16) {
                GridRow {
                    preferencesTray
                    notificationsTray
                }
                GridRow {
                    reportsTray
                    systemTray
                }
                GridRow {
                    usageTray
                    Color.clear.frame(height: 0)
                }
            }

            fundPolicyTray
            advancedToolsTray
            deskBackupTray
            operationsTray
            MacBureauMacTrays()
        }
    }

    // MARK: Profile

    private var profileTray: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack(alignment: .top, spacing: 16) {
                MacBureauSeal(name: account?.name ?? account?.email ?? "", size: 52)
                VStack(alignment: .leading, spacing: 0) {
                    Text("Profile")
                        .font(.custom(BSHType.bureauSerif, size: 23))
                        .tracking(-0.23)
                        .foregroundStyle(ink.ink)
                        .frame(height: 28)
                    Text(account?.name ?? account?.email ?? "")
                        .font(BSHType.bureauSans(14))
                        .tracking(-0.084)
                        .foregroundStyle(ink.ink)
                        .frame(height: 20)
                        .padding(.top, 2)
                    Text(accountEmail)
                        .font(BSHType.bureauSans(12))
                        .foregroundStyle(ink.muted)
                        .frame(height: 16)
                    HStack(spacing: 8) {
                        ForEach([account?.workspace, account?.role, account?.plan].compactMap { $0 }.filter { !$0.isEmpty }, id: \.self) { item in
                            Text(item)
                        }
                    }
                    .font(BSHType.bureauSans(11))
                    .tracking(0.066)
                    .foregroundStyle(ink.muted)
                    .frame(height: 14)
                    .padding(.top, 8)
                }
                Spacer(minLength: 0)
            }
            HStack(spacing: 8) {
                statBox("Permissions", "\(permissions.count) grants")
                statBox("Seats", "\(profile?.team?.licensedSeats ?? 0) licensed")
                statBox("Usage", "\(profile?.usage?.analyticsEvents ?? 0) events")
            }
        }
        .bureauTray()
    }

    private func statBox(_ label: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label)
                .font(BSHType.bureauSans(11))
                .tracking(0.066)
                .foregroundStyle(ink.muted)
                .frame(height: 14)
            Text(value)
                .font(BSHType.bureauSans(14, weight: .medium))
                .tracking(-0.084)
                .foregroundStyle(ink.ink)
                .frame(height: 20)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 9, style: .circular).fill(ink.fillTertiary))
    }

    // MARK: Preferences

    private var preferencesTray: some View {
        VStack(alignment: .leading, spacing: 0) {
            MacBureauTrayTitle(title: "Preferences", icon: "languages")

            labeled("Language", top: 16) {
                MacBureauSegmented(
                    [("en", "EN"), ("zh", "中文")],
                    selection: preferenceBinding(\.language, key: "language", default: "en")
                )
            }

            labeled("Appearance", top: 20) {
                MacBureauSegmented(
                    MacAppearance.allCases.map { (value: $0, title: $0.title, icon: Optional($0.icon)) },
                    selection: Binding(
                        get: { appearance },
                        set: { next in
                            appearance = next
                            UserDefaults.standard.set(next.rawValue, forKey: MacAppearance.storageKey)
                            next.apply()
                        }
                    )
                )
            }

            labeled("Design", top: 20) {
                VStack(alignment: .leading, spacing: 0) {
                    MacBureauSegmented(
                        BSHDesignCards.order.map { ($0, $0.title) },
                        selection: $design.design
                    )
                    Text("Summit Glass is the original look and the default. Bureau lays the page on a desk, white by day and black by night, or a color picked below when Bureau is on. Folio is paper and ink.")
                        .font(BSHType.bureauSans(12))
                        .foregroundStyle(ink.muted)
                        .bureauLines(16, size: 12)
                        .fixedSize(horizontal: false, vertical: true)
                        .padding(.top, 6)
                    if design.design == .bureau {
                        MacBureauKicker("Desk color")
                            .padding(.top, 16)
                            .padding(.bottom, 8)
                        MacBureauDeskSwatches(selection: $design.bureauDesk)
                    }
                }
            }

            HStack(spacing: 12) {
                VStack(alignment: .leading, spacing: 0) {
                    Text("Welcome tour")
                        .font(BSHType.bureauSans(14))
                        .tracking(-0.084)
                        .foregroundStyle(ink.secondary)
                        .frame(height: 20)
                    Text("The walkthrough shown on first sign-in: desks, memos, markets and Warren.")
                        .font(BSHType.bureauSans(12))
                        .foregroundStyle(ink.muted)
                        .bureauLines(16, size: 12)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Spacer(minLength: 0)
                MacBureauButton("Replay", size: .small) { store.replayWelcomeTour() }
            }
            .padding(.horizontal, 4)
            .padding(.vertical, 8)
            .padding(.top, 20)

            HStack(spacing: 12) {
                Text("Compact density")
                    .font(BSHType.bureauSans(14))
                    .tracking(-0.084)
                    .foregroundStyle(ink.secondary)
                Spacer(minLength: 0)
                MacBureauSwitch(
                    isOn: preferenceBinding(\.compactDensity, key: "compact_density", default: false),
                    disabled: saving == "compact_density"
                )
            }
            .padding(.horizontal, 4)
            .padding(.vertical, 8)
            .padding(.top, 20)

            labeled("Parallel report runs", top: 20) {
                VStack(alignment: .leading, spacing: 8) {
                    MacBureauSegmented(
                        [1, 2, 3, 4].map { ($0, "\($0)") },
                        selection: preferenceBinding(\.memoParallelRuns, key: "memo_parallel_runs", default: 2),
                        disabled: saving == "memo_parallel_runs"
                    )
                    hint("How many companies can run an investigation or report at once. Extra runs wait in a queue. News/Updates auto-runs keep 2 separate slots.")
                }
            }

            labeled("Research engine", top: 20) {
                VStack(alignment: .leading, spacing: 8) {
                    MacBureauSegmented(
                        [("claude", "Claude"), ("gemini", "Gemini"), ("gemini-only", "Gemini only")],
                        selection: preferenceBinding(\.researchEngine, key: "research_engine", default: "claude"),
                        disabled: saving == "research_engine"
                    )
                    hint("Which model answers the team dossier, the daily desk note and the company news sweep. Gemini falls back to Claude if a call fails; Gemini only reports the failure instead. Reports are not affected — each report picks its engine when you start it.")
                }
            }

            labeled("Warren", top: 20) {
                VStack(alignment: .leading, spacing: 8) {
                    MacBureauSegmented(
                        [("claude", "Claude"), ("gemini", geminiLabel)],
                        selection: Binding(
                            get: { settings?.warren?.engine ?? prefs?.warrenEngine ?? "claude" },
                            set: { value in Task { await patch("warren_engine", value) } }
                        ),
                        disabled: saving == "warren_engine"
                    )
                    hint(warrenHint)
                    if settings?.warren?.geminiAvailable == false {
                        Text("No Gemini API key is set, so nothing can stand in for Claude. Add GEMINI_API_KEY to the server's .env.")
                            .font(BSHType.bureauSans(11))
                            .foregroundStyle(ink.warning)
                    } else if let resting = settings?.warren?.claudeResting, !resting.isEmpty {
                        Text("Claude is out right now: \(resting). \(geminiLabel) is answering Warren.")
                            .font(BSHType.bureauSans(11))
                            .foregroundStyle(ink.muted)
                    }
                }
            }
        }
        .frame(maxHeight: .infinity, alignment: .top)
        .bureauTray()
    }

    /// The Gemini model's name as the website formats it ("gemini-3.8-flash" → "Gemini 3.8 Flash").
    private var geminiLabel: String {
        guard let raw = settings?.warren?.geminiModel, !raw.isEmpty else { return "Gemini" }
        return raw.split(separator: "-").map { part in
            let s = String(part)
            return s.first?.isLetter == true ? s.prefix(1).uppercased() + s.dropFirst() : s
        }
        .joined(separator: " ")
    }

    private var warrenHint: String {
        let engine = settings?.warren?.engine ?? prefs?.warrenEngine ?? "claude"
        if engine == "gemini" {
            return "\(geminiLabel) answers Warren and searches the web when a question needs it. Claude answers only if \(geminiLabel) fails."
        }
        return "Claude answers Warren. When Claude is out of tokens or can't be reached, \(geminiLabel) answers instead, and the answer says so."
    }

    // MARK: Notifications

    private var notificationsTray: some View {
        VStack(alignment: .leading, spacing: 0) {
            MacBureauTrayTitle(title: "Notifications", icon: "bell")
            VStack(spacing: 4) {
                switchRow("Weekly summary", \.weeklySummary, key: "weekly_summary")
                switchRow("Stock auto-refresh", \.stockAutoRefresh, key: "stock_auto_refresh")
                switchRow("Agent task alerts", \.agentAlerts, key: "agent_alerts")
            }
            .padding(.top, 16)
        }
        .frame(maxHeight: .infinity, alignment: .top)
        .bureauTray()
    }

    private func switchRow(_ title: String, _ path: KeyPath<MacWorkspaceSettings.Preferences, Bool?>, key: String) -> some View {
        HStack(spacing: 12) {
            Text(title)
                .font(BSHType.bureauSans(14))
                .tracking(-0.084)
                .foregroundStyle(ink.secondary)
            Spacer(minLength: 0)
            MacBureauSwitch(isOn: preferenceBinding(path, key: key, default: false), disabled: saving == key)
        }
        .padding(.horizontal, 4)
        .padding(.vertical, 8)
    }

    // MARK: Reports

    /// The memo template in force: the server's own default is the IC template.
    private var memoTemplate: String {
        let raw = settings?.memoTemplateEffective ?? prefs?.memoTemplateEffective ?? settings?.memoTemplate ?? prefs?.memoTemplate
        return raw == "standard" ? "standard" : "ic_v2"
    }

    private var reportsTray: some View {
        VStack(alignment: .leading, spacing: 0) {
            MacBureauTrayTitle(title: "Reports", icon: "file-text")
            MacBureauKicker("Memo template")
                .padding(.top, 16)
                .padding(.bottom, 8)
            VStack(spacing: 8) {
                templateOption(
                    "standard",
                    title: "Standard memo (v1)",
                    detail: "The earlier 5-section memo most reports on file use: Executive Summary, Company Overview, Investment Highlights, Investment Risk, Financial Forecast & Valuation, then the decision. About 6,000–9,000 words."
                )
                templateOption(
                    "ic_v2",
                    title: "Founder's IC template (default)",
                    detail: "The founder's 12-section investment-committee framework: market, product, competition, moat, financials, team, valuation, returns and exit, with a scorecard out of 100, a Strong Buy–Pass verdict, clickable source citations and charts. About twice as long as the standard memo."
                )
            }
            hint("Applies to Investment Memo (Late-Stage) and Investment Report (Auto). Buffett-Method memos are unaffected. The Generate dialog can still switch it for a single run.")
                .padding(.top, 8)
            if memoTemplateNotSaved {
                Text("This server keeps its own template; the choice wasn't saved.")
                    .font(BSHType.bureauSans(11))
                    .foregroundStyle(ink.warning)
                    .padding(.top, 4)
            }
        }
        .frame(maxHeight: .infinity, alignment: .top)
        .bureauTray()
    }

    private func templateOption(_ value: String, title: String, detail: String) -> some View {
        let chosen = memoTemplate == value
        return Button {
            guard !chosen, saving != "memo_template" else { return }
            Task {
                memoTemplateNotSaved = false
                await patch("memo_template", value)
                if loadError == nil && memoTemplate != value { memoTemplateNotSaved = true }
            }
        } label: {
            HStack(alignment: .top, spacing: 12) {
                ZStack {
                    Circle()
                        .fill(chosen ? ink.accent : .clear)
                        .overlay(Circle().strokeBorder(chosen ? ink.accent : ink.ruleStrong, lineWidth: 1))
                    if chosen {
                        LucideIcon("check", size: 10).foregroundStyle(.white)
                    }
                }
                .frame(width: 16, height: 16)
                .padding(.top, 2)
                VStack(alignment: .leading, spacing: 2) {
                    Text(title)
                        .font(BSHType.bureauSans(14, weight: .medium))
                        .tracking(-0.084)
                        .foregroundStyle(ink.ink)
                    Text(detail)
                        .font(BSHType.bureauSans(12))
                        .foregroundStyle(ink.muted)
                        .bureauLines(16, size: 12)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Spacer(minLength: 0)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 10)
            .background(RoundedRectangle(cornerRadius: 9, style: .circular).fill(chosen ? ink.accent.opacity(0.05) : .clear))
            .overlay(RoundedRectangle(cornerRadius: 9, style: .circular).strokeBorder(chosen ? ink.accent : ink.rule, lineWidth: 1))
            .contentShape(RoundedRectangle(cornerRadius: 9))
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(chosen ? .isSelected : [])
    }

    // MARK: System

    private var systemTray: some View {
        VStack(alignment: .leading, spacing: 0) {
            MacBureauTrayTitle(title: "System", icon: "database")
            VStack(spacing: 6) {
                MacBureauRow(label: "Workspace role", value: account?.role ?? "adapter", valueTone: ink.accentInk)
                MacBureauRow(label: "Account", value: accountEmail)
            }
            .padding(.top, 16)

            HStack(spacing: 8) {
                if signedIn {
                    MacBureauButton("Change password", size: .small) {
                        MacConfig.openInBrowser(MacConfig.webURL(path: "change-password"))
                    }
                    MacBureauButton("Sign out everywhere else", size: .small) {
                        Task { await signOutElsewhere() }
                    }
                } else {
                    MacBureauButton("Sign in", size: .small) { store.showLoginSheet = true }
                }
                if permissions.contains("users:manage") {
                    MacBureauButton("Manage accounts", size: .small) {
                        withAnimation(.easeInOut(duration: 0.18)) {
                            store.openInEmbeddedBrowser(MacConfig.webURL(path: "accounts"))
                        }
                    }
                }
                if let sessionsNotice {
                    Text(sessionsNotice).font(BSHType.bureauSans(12)).foregroundStyle(ink.muted)
                }
            }
            .padding(.top, 12)

            Button {
                withAnimation(.easeInOut(duration: 0.15)) { systemDetailsOpen.toggle() }
            } label: {
                HStack(spacing: 6) {
                    Image(systemName: "triangle.fill")
                        .font(.system(size: 6))
                        .rotationEffect(.degrees(systemDetailsOpen ? 180 : 90))
                    Text("System details")
                }
                .font(BSHType.bureauSans(12))
                .foregroundStyle(ink.muted)
                .padding(4)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .padding(.top, 12)

            if systemDetailsOpen {
                VStack(alignment: .leading, spacing: 4) {
                    if let scope = settings?.adapterScope, !scope.isEmpty {
                        Text(scope)
                            .padding(.horizontal, 12)
                            .padding(.vertical, 8)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .background(RoundedRectangle(cornerRadius: 11, style: .circular).fill(ink.fillTertiary))
                    }
                    ForEach(profile?.status ?? [], id: \.key) { pair in
                        HStack(spacing: 12) {
                            Text(pair.key.replacingOccurrences(of: "_", with: " "))
                            Spacer(minLength: 0)
                            Text(pair.value).foregroundStyle(ink.ink)
                        }
                        .padding(.horizontal, 4)
                        .padding(.vertical, 4)
                    }
                }
                .font(BSHType.bureauSans(12))
                .foregroundStyle(ink.muted)
                .padding(.top, 8)
            }
        }
        .frame(maxHeight: .infinity, alignment: .top)
        .bureauTray()
    }

    // MARK: Usage

    private var usageTray: some View {
        VStack(alignment: .leading, spacing: 0) {
            MacBureauTrayTitle(title: "Usage", icon: "sliders-horizontal")
            VStack(spacing: 6) {
                MacBureauRow(label: "Plan", value: account?.plan ?? "")
                MacBureauRow(label: "Permissions", value: "\(permissions.count) grants")
            }
            .padding(.top, 16)
        }
        .bureauTray()
    }

    // MARK: Fund policy

    private var fundPolicyTray: some View {
        MacBureauFundPolicy(canEdit: permissions.contains("settings:update"))
    }

    // MARK: Advanced tools

    private var advancedToolsTray: some View {
        VStack(alignment: .leading, spacing: 0) {
            MacBureauTrayTitle(title: "Advanced tools")
            hint("Workbench, Stats, and Labs live here so Home keeps Market and the Markets rail stays Pulse.", size: 12)
                .padding(.top, 4)
            HStack(spacing: 8) {
                toolLink("Workbench", icon: "activity", path: "stock-research")
                toolLink("Stats", icon: "chart-column", path: "trader-stats")
                toolLink("Labs", icon: "flask-conical", path: "innovation-lab")
            }
            .padding(.top, 16)
        }
        .bureauTray()
    }

    private func toolLink(_ title: String, icon: String, path: String) -> some View {
        MacBureauToolLink(title: title, icon: icon, ink: ink) {
            withAnimation(.easeInOut(duration: 0.18)) {
                store.openInEmbeddedBrowser(MacConfig.webURL(path: path))
            }
        }
    }

    // MARK: Desk backup

    private var deskBackupTray: some View {
        VStack(alignment: .leading, spacing: 0) {
            MacBureauTrayTitle(title: "Market desk backup")
            hint("Export or restore watchlists, alert rules, book lots, notes, and chart prefs.", size: 12)
                .padding(.top, 4)
            HStack(spacing: 8) {
                MacBureauButton("Export desk", icon: "download", busy: deskBusy) { Task { await exportDesk() } }
                    .disabled(deskBusy)
                MacBureauButton("Import desk", icon: "upload") { Task { await importDesk() } }
                    .disabled(deskBusy)
            }
            .padding(.top, 16)
            if let deskMessage { hint(deskMessage, size: 12).padding(.top, 8) }
            if let deskError {
                Text(deskError).font(BSHType.bureauSans(12)).foregroundStyle(ink.danger).padding(.top, 8)
            }
        }
        .bureauTray()
    }

    // MARK: Operations

    private var operationsTray: some View {
        VStack(alignment: .leading, spacing: 0) {
            MacBureauTrayTitle(title: "Operations")
            hint("Administrative refresh actions stay available without competing with search.", size: 12)
                .padding(.top, 4)
            HStack(spacing: 8) {
                MacBureauButton(regenerating ? "Regenerating…" : "Regenerate all", busy: regenerating) { confirmingRegen = true }
                    .disabled(regenerating || !store.canRunTasks)
                MacBureauButton(refreshingStockViews ? "Refreshing…" : "Refresh stock views", icon: "refresh-cw", busy: refreshingStockViews) {
                    confirmingStockViews = true
                }
                .disabled(refreshingStockViews || !store.canRunTasks)
            }
            .padding(.top, 16)
            if let operationsMessage { hint(operationsMessage, size: 12).padding(.top, 8) }
            if let operationsError {
                Text(operationsError).font(BSHType.bureauSans(12)).foregroundStyle(ink.danger).padding(.top, 8)
            }
        }
        .bureauTray()
    }

    // MARK: Pieces

    private func labeled<Control: View>(_ title: String, top: CGFloat, @ViewBuilder control: () -> Control) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            MacBureauKicker(title)
            control()
        }
        .padding(.top, top)
    }

    private func hint(_ text: String, size: CGFloat = 11) -> some View {
        Text(text)
            .font(BSHType.bureauSans(size))
            .tracking(size == 11 ? 0.066 : 0)
            .foregroundStyle(ink.muted)
            .bureauLines(size == 11 ? 14 : 16, size: size)
            .fixedSize(horizontal: false, vertical: true)
    }

    /// A preference as a binding: reads the server's value, writes by PATCH.
    private func preferenceBinding<T: Equatable>(_ path: KeyPath<MacWorkspaceSettings.Preferences, T?>, key: String, default value: T) -> Binding<T> {
        Binding(
            get: { prefs?[keyPath: path] ?? value },
            set: { next in Task { await patch(key, next) } }
        )
    }

    // MARK: Loading and saving

    private func load() async {
        loading = true
        loadError = nil
        async let workspace = try? MacAPIClient.shared.workspaceSettings()
        async let user = try? MacAPIClient.shared.userCenter()
        let (w, u) = await (workspace, user)
        settings = w
        profile = u
        if w == nil && u == nil { loadError = "Could not load settings from \(MacConfig.baseURL.host ?? "the server")." }
        loading = false
    }

    private func patch(_ key: String, _ value: Any) async {
        saving = key
        loadError = nil
        defer { saving = nil }
        do {
            settings = try await MacAPIClient.shared.updateWorkspaceSettings([key: value])
        } catch {
            loadError = error.localizedDescription
        }
    }

    private func signOutElsewhere() async {
        do {
            try await MacAPIClient.shared.revokeOtherSessions()
            sessionsNotice = "Signed out everywhere else."
        } catch {
            sessionsNotice = error.localizedDescription
        }
    }

    private func regenerateAll() async {
        regenerating = true
        operationsMessage = nil
        operationsError = nil
        defer { regenerating = false }
        do {
            let result = try await MacAPIClient.shared.regenerateAllCompanies()
            let total = result.totalCount ?? 0
            if total == 0 {
                operationsMessage = "No companies to regenerate."
            } else if result.status == "already_running" {
                operationsMessage = "Already regenerating \(total) companies."
            } else {
                operationsMessage = "Regenerating \(total) companies (\(result.publicTraderCount ?? 0) with stock views)."
            }
        } catch {
            operationsError = "Could not start the regeneration."
        }
    }

    private func refreshStockViews() async {
        refreshingStockViews = true
        operationsMessage = nil
        operationsError = nil
        defer { refreshingStockViews = false }
        do {
            let result = try await MacAPIClient.shared.refreshAllStockViews()
            let total = result.totalCount ?? 0
            if total == 0 {
                operationsMessage = "No listed companies to refresh."
            } else if result.status == "already_running" {
                operationsMessage = "Already refreshing \(total) stock views."
            } else {
                operationsMessage = "Refreshing \(result.queuedCount ?? 0) of \(total) stock views."
            }
        } catch {
            operationsError = "Could not start the refresh."
        }
    }

    private func exportDesk() async {
        deskBusy = true
        deskError = nil
        deskMessage = nil
        defer { deskBusy = false }
        do {
            let data = try await MacAPIClient.shared.deskPrefsSnapshot()
            let payload: [String: Any] = [
                "schema": "bsh.marketDesk.v1",
                "exported_at": ISO8601DateFormatter().string(from: Date()),
                "data": data,
            ]
            let json = try JSONSerialization.data(withJSONObject: payload, options: [.prettyPrinted, .sortedKeys])
            let panel = NSSavePanel()
            panel.allowedContentTypes = [.json]
            panel.nameFieldStringValue = "bsh-desk-\(String(ISO8601DateFormatter().string(from: Date()).prefix(10))).json"
            guard panel.runModal() == .OK, let url = panel.url else { return }
            try json.write(to: url)
            deskMessage = "Exported \(data.count) desk settings."
        } catch {
            deskError = "Could not export the desk."
        }
    }

    private func importDesk() async {
        let panel = NSOpenPanel()
        panel.allowedContentTypes = [.json]
        panel.allowsMultipleSelection = false
        guard panel.runModal() == .OK, let url = panel.url else { return }
        deskBusy = true
        deskError = nil
        deskMessage = nil
        defer { deskBusy = false }
        do {
            let raw = try JSONSerialization.jsonObject(with: Data(contentsOf: url))
            let root = raw as? [String: Any]
            guard let data = (root?["data"] as? [String: Any]) ?? root else {
                deskError = "That file isn't a desk backup."
                return
            }
            let desk = MacAPIClient.deskPrefs(fromBackup: data)
            _ = try await MacAPIClient.shared.saveDeskPrefs(watchlist: desk.watchlist, lots: desk.lots, rules: desk.rules)
            await store.refreshDeskPrefs()
            deskMessage = "Restored \(desk.watchlist.count) watchlist tickers, \(desk.lots.count) book lots and \(desk.rules.count) alert rules."
        } catch {
            deskError = "Could not import the desk."
        }
    }
}

/// An initials seal on a hashed color, as the website's tinted monogram draws it.
struct MacBureauSeal: View {
    let name: String
    var size: CGFloat = 52

    private static let tints: [BSHRGB] = [
        BSHRGB(10, 132, 255), BSHRGB(88, 86, 214), BSHRGB(175, 82, 222), BSHRGB(255, 45, 85), BSHRGB(255, 69, 58),
        BSHRGB(255, 149, 0), BSHRGB(48, 176, 199), BSHRGB(50, 173, 230), BSHRGB(0, 199, 190), BSHRGB(52, 199, 89),
    ]

    /// The website's hash: 31·h + each UTF-16 unit, unsigned 32-bit.
    private var tint: BSHRGB {
        var hash: UInt32 = 0
        for unit in name.utf16 { hash = hash &* 31 &+ UInt32(unit) }
        return Self.tints[Int(hash % 10)]
    }

    /// Two letters: first and last word, or the first two letters of one word.
    private var initials: String {
        let base = name.contains("@") ? String(name.split(separator: "@").first ?? "") : name
        let parts = base.split(whereSeparator: \.isWhitespace)
        if parts.count >= 2, let a = parts.first?.first, let b = parts.last?.first { return "\(a)\(b)".uppercased() }
        if let one = parts.first, one.count >= 2 { return String(one.prefix(2)).uppercased() }
        return parts.first.map { String($0.prefix(1)).uppercased() } ?? "?"
    }

    var body: some View {
        Text(initials)
            .font(BSHType.bureauSans(size * 0.37, weight: .semibold))
            .tracking(size * 0.0037)
            .foregroundStyle(.white)
            .shadow(color: .black.opacity(0.18), radius: 0.5, y: 0.5)
            .frame(width: size, height: size)
            .background(
                Circle().fill(LinearGradient(
                    colors: [.bshFixed(tint), .bshFixed(tint, opacity: 0.72)],
                    startPoint: UnitPoint(x: 0.21, y: 0.09), endPoint: UnitPoint(x: 0.79, y: 0.91)
                ))
            )
            .overlay(Circle().strokeBorder(Color.black.opacity(0.08), lineWidth: 0.5))
    }
}

/// Bureau's desk colors, as the website's picker shows them: a swatch each, named under
/// it; the chosen one ringed in brass with a check.
struct MacBureauDeskSwatches: View {
    @Environment(\.colorScheme) private var colorScheme
    @Binding var selection: BSHBureauDesk

    private static let names: [BSHBureauDesk: String] = [
        .onyx: "Onyx & White", .green: "Bottle green", .maroon: "Maroon", .navy: "Navy",
        .aubergine: "Aubergine", .tobacco: "Tobacco", .graphite: "Graphite",
    ]

    var body: some View {
        let ink = MacBureauPageInk(scheme: colorScheme)
        HStack(alignment: .top, spacing: 4) {
            ForEach(BSHBureauDesk.allCases) { desk in
                MacBureauDeskSwatch(desk: desk, name: Self.names[desk] ?? desk.title, chosen: selection == desk, ink: ink) {
                    selection = desk
                }
            }
        }
    }
}

private struct MacBureauDeskSwatch: View {
    let desk: BSHBureauDesk
    let name: String
    let chosen: Bool
    let ink: MacBureauPageInk
    let action: () -> Void
    @State private var hovered = false

    var body: some View {
        Button(action: action) {
            VStack(spacing: 7) {
                BSHDeskSwatch(desk: desk, size: 30)
                    .overlay(Circle().strokeBorder(ink.dark ? Color.white.opacity(0.32) : Color.black.opacity(0.16), lineWidth: 1))
                    .overlay {
                        if chosen {
                            Circle().inset(by: -4).stroke(ink.accent, lineWidth: 2).padding(-0)
                        }
                    }
                    .overlay(alignment: .bottomTrailing) {
                        if chosen {
                            LucideIcon("check", size: 10)
                                .foregroundStyle(.white)
                                .frame(width: 16, height: 16)
                                .background(Circle().fill(ink.accent))
                                .shadow(color: .black.opacity(0.3), radius: 1, y: 1)
                                .offset(x: 5, y: 5)
                        }
                    }
                // The chosen desk's name is set in ink, semibold; a name wraps between
                // words only, as it does on the page.
                Text(name)
                    .font(BSHType.bureauSans(11, weight: chosen ? .semibold : .regular))
                    .foregroundStyle(chosen ? ink.ink : ink.secondary)
                    .multilineTextAlignment(.center)
                    .bureauLines(14, size: 11)
                    .frame(width: 56)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding(.top, 8)
            .padding(.bottom, 6)
            .frame(width: 56)
            .background(RoundedRectangle(cornerRadius: 10, style: .circular).fill(hovered ? ink.ink(0.05) : .clear))
            .contentShape(RoundedRectangle(cornerRadius: 10))
        }
        .buttonStyle(.plain)
        .onHover { hovered = $0 }
        .help(name)
        .accessibilityAddTraits(chosen ? .isSelected : [])
    }
}

/// A link to a web-only tool: a band of the sheet's fill with a brass glyph.
private struct MacBureauToolLink: View {
    let title: String
    let icon: String
    let ink: MacBureauPageInk
    let action: () -> Void
    @State private var hovered = false

    var body: some View {
        Button(action: action) {
            HStack(spacing: 12) {
                LucideIcon(icon, size: 16).foregroundStyle(ink.accent)
                Text(title)
                    .font(BSHType.bureauSans(14, weight: .medium))
                    .tracking(-0.084)
                    .foregroundStyle(ink.ink)
                Spacer(minLength: 0)
            }
            .padding(12)
            .frame(maxWidth: .infinity)
            .background(RoundedRectangle(cornerRadius: 11, style: .circular).fill(hovered ? ink.fillSecondary : ink.fillTertiary))
            .contentShape(RoundedRectangle(cornerRadius: 11))
        }
        .buttonStyle(.plain)
        .onHover { hovered = $0 }
    }
}

// MARK: - Fund return policy

/// The return each stage's memos are judged against: the website's editor, stage by stage.
private struct MacBureauFundPolicy: View {
    @Environment(\.colorScheme) private var colorScheme
    let canEdit: Bool

    private static let stages = ["early", "growth", "late"]
    private static let stageNames = ["early": "Early stage", "growth": "Growth stage", "late": "Late stage"]

    private struct Field {
        let key: WritableKeyPath<Draft, String>
        let saved: KeyPath<MacFundPolicy.Stage, Double?>
        let label: String
        let unit: String
        let range: ClosedRange<Double>
        let value: (String) -> String
    }

    private struct Draft: Equatable {
        var moic = "", irr = "", hold = "", position = "", basis = "gross"
    }

    private static let fields: [Field] = [
        Field(key: \.moic, saved: \.targetMoic, label: "Target MOIC", unit: "x", range: 1...50, value: { "\($0)x" }),
        Field(key: \.irr, saved: \.targetIrrPct, label: "Target IRR", unit: "%", range: 0...500, value: { "\($0)%" }),
        Field(key: \.hold, saved: \.maxHoldYears, label: "Longest hold", unit: "years", range: 0.5...30, value: { "\($0) years" }),
        Field(key: \.position, saved: \.maxPositionPct, label: "Largest position", unit: "% of fund", range: 0...100, value: { "\($0)% of fund" }),
    ]

    @State private var policy: MacFundPolicy?
    @State private var drafts: [String: Draft] = [:]
    @State private var loading = true
    @State private var loadFailed = false
    @State private var saving = false
    @State private var saved = false
    @State private var error: String?

    private var ink: MacBureauPageInk { MacBureauPageInk(scheme: colorScheme) }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 8) {
                MacBureauTrayTitle(title: "Fund return policy", icon: "scale")
                if let policy {
                    MacBureauChip(
                        text: policy.isSet == true ? "In force" : "Not set",
                        foreground: policy.isSet == true ? ink.successInk : ink.secondary,
                        background: policy.isSet == true ? ink.successSoft : ink.fillSecondary
                    )
                }
            }
            Text("The return each stage's investment memos are judged against. Once a stage has a target MOIC or IRR, its memos state the hurdle and flag any call whose base case misses it. Until you set one, nothing changes: memos carry no hurdle.")
                .font(BSHType.bureauSans(12))
                .foregroundStyle(ink.muted)
                .bureauLines(16, size: 12)
                .frame(maxWidth: 768, alignment: .leading)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.top, 4)

            if loading {
                Text("Loading the fund policy…").font(BSHType.bureauSans(14)).foregroundStyle(ink.muted).padding(.top, 16)
            } else if loadFailed {
                Text("Could not load the fund policy.").font(BSHType.bureauSans(14)).foregroundStyle(ink.dangerInk).padding(.top, 16)
            } else {
                HStack(alignment: .top, spacing: 12) {
                    ForEach(Self.stages, id: \.self) { stage in stageBox(stage) }
                }
                .padding(.top, 16)

                Text("Net means after SPV fees and carry. The longest hold is the period the target assumes; the largest position caps one company's share of the fund.")
                    .font(BSHType.bureauSans(11))
                    .tracking(0.066)
                    .foregroundStyle(ink.muted)
                    .padding(.top, 8)
                if let context = contextLine {
                    Text(context).font(BSHType.bureauSans(11)).foregroundStyle(ink.muted).padding(.top, 4)
                }

                if canEdit {
                    HStack(spacing: 8) {
                        MacBureauButton(saving ? "Saving…" : "Save policy", kind: .filled, size: .small, busy: saving) {
                            Task { await save() }
                        }
                        .disabled(!dirty || invalid || saving)
                        MacBureauButton("Discard changes", size: .small) {
                            resetDrafts()
                            error = nil
                        }
                        .disabled(!dirty || saving)
                        if saved && !dirty {
                            Text("Saved. Runs started from now on use it.").font(BSHType.bureauSans(12)).foregroundStyle(ink.successInk)
                        }
                        if let error {
                            Text(error).font(BSHType.bureauSans(12)).foregroundStyle(ink.dangerInk)
                        }
                    }
                    .padding(.top, 12)
                } else {
                    Text("Only admins and partners can change the policy.")
                        .font(BSHType.bureauSans(11))
                        .foregroundStyle(ink.muted)
                        .padding(.top, 12)
                }
                if let updated = updatedLine {
                    Text(updated).font(BSHType.bureauSans(11)).foregroundStyle(ink.muted).padding(.top, 4)
                }
            }
        }
        .bureauTray()
        .task { await load() }
    }

    private func stageBox(_ stage: String) -> some View {
        let isSet = stageIsSet(stage)
        return VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text(Self.stageNames[stage] ?? stage)
                    .font(BSHType.bureauSans(14, weight: .semibold))
                    .tracking(-0.084)
                    .foregroundStyle(ink.ink)
                Spacer(minLength: 4)
                Text(isSet ? "Set" : "Not set")
                    .font(BSHType.bureauSans(11))
                    .foregroundStyle(isSet ? ink.successInk : ink.muted)
            }
            if canEdit {
                VStack(spacing: 8) {
                    ForEach(Self.fields, id: \.label) { field in
                        HStack(spacing: 6) {
                            Text(field.label).foregroundStyle(ink.secondary)
                            Spacer(minLength: 4)
                            MacBureauField(
                                placeholder: "—",
                                text: Binding(
                                    get: { drafts[stage]?[keyPath: field.key] ?? "" },
                                    set: { drafts[stage, default: Draft()][keyPath: field.key] = $0 }
                                ),
                                size: 12,
                                height: 28,
                                alignment: .trailing
                            )
                            .frame(width: 80)
                            .overlay(RoundedRectangle(cornerRadius: 10).strokeBorder(isInvalid(stage, field) ? ink.danger : .clear, lineWidth: 1))
                            Text(field.unit)
                                .font(BSHType.bureauSans(11))
                                .foregroundStyle(ink.muted)
                                .frame(width: 64, alignment: .leading)
                        }
                    }
                    HStack(spacing: 6) {
                        Text("Basis").foregroundStyle(ink.secondary)
                        Spacer(minLength: 4)
                        MacBureauSegmented(
                            [("gross", "Gross"), ("net", "Net")],
                            selection: Binding(
                                get: { drafts[stage]?.basis ?? "gross" },
                                set: { drafts[stage, default: Draft()].basis = $0 }
                            )
                        )
                    }
                }
                .font(BSHType.bureauSans(12))
            } else {
                VStack(spacing: 4) {
                    ForEach(Self.fields, id: \.label) { field in
                        HStack {
                            Text(field.label).foregroundStyle(ink.secondary)
                            Spacer()
                            Text(savedValue(stage, field)).foregroundStyle(ink.ink)
                        }
                    }
                    HStack {
                        Text("Basis").foregroundStyle(ink.secondary)
                        Spacer()
                        Text(savedBasis(stage)).foregroundStyle(ink.ink)
                    }
                }
                .font(BSHType.bureauSans(12).monospacedDigit())
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .topLeading)
        .background(RoundedRectangle(cornerRadius: 9, style: .circular).fill(ink.fillTertiary))
    }

    private func stageIsSet(_ stage: String) -> Bool {
        guard let entry = policy?.stages[stage] else { return false }
        return entry.targetMoic != nil || entry.targetIrrPct != nil
    }

    private func savedValue(_ stage: String, _ field: Field) -> String {
        guard let value = policy?.stages[stage]?[keyPath: field.saved] else { return "Not set" }
        return field.value(Self.format(value))
    }

    private func savedBasis(_ stage: String) -> String {
        guard let entry = policy?.stages[stage] else { return "Not set" }
        return entry.basis == "net" ? "Net" : "Gross"
    }

    private static func format(_ value: Double) -> String {
        value == value.rounded() ? String(Int(value)) : String(value)
    }

    private func draft(from saved: MacFundPolicy?) -> [String: Draft] {
        var out: [String: Draft] = [:]
        for stage in Self.stages {
            var d = Draft()
            if let entry = saved?.stages[stage] {
                for field in Self.fields {
                    d[keyPath: field.key] = entry[keyPath: field.saved].map(Self.format) ?? ""
                }
                d.basis = entry.basis == "net" ? "net" : "gross"
            }
            out[stage] = d
        }
        return out
    }

    private func resetDrafts() { drafts = draft(from: policy) }

    private var dirty: Bool { drafts != draft(from: policy) }

    private func number(_ raw: String) -> Double?? {
        let text = raw.trimmingCharacters(in: .whitespaces)
        if text.isEmpty { return .some(nil) }
        guard let value = Double(text), value.isFinite else { return nil }
        return .some(value)
    }

    private func isInvalid(_ stage: String, _ field: Field) -> Bool {
        guard let raw = drafts[stage]?[keyPath: field.key] else { return false }
        switch number(raw) {
        case .none: return true
        case .some(.none): return false
        case .some(.some(let value)): return !field.range.contains(value)
        }
    }

    private var invalid: Bool {
        Self.stages.contains { stage in Self.fields.contains { isInvalid(stage, $0) } }
    }

    private var contextLine: String? {
        guard let context = policy?.context else { return nil }
        func musd(_ value: Double?) -> String? {
            guard let value, value > 0 else { return nil }
            return value >= 1000 ? "$\(Self.format((value / 1000 * 100).rounded() / 100))B" : "$\(Self.format((value * 100).rounded() / 100))M"
        }
        var parts: [String] = []
        if let fund = musd(context.fundSizeMusd) { parts.append("fund size \(fund)") }
        if let low = musd(context.checkSizeMinMusd), let high = musd(context.checkSizeMaxMusd) { parts.append("check size \(low)–\(high)") }
        return parts.isEmpty ? nil : "For reference, from the Thesis and Reserves settings: \(parts.joined(separator: "; "))"
    }

    private var updatedLine: String? {
        guard let at = policy?.updatedAt, !at.isEmpty else { return nil }
        let date = String(at.prefix(10))
        if let who = policy?.updatedBy, !who.isEmpty { return "Last saved \(date) by \(who)." }
        return "Last saved \(date)."
    }

    private func load() async {
        loading = true
        loadFailed = false
        do {
            let loaded = try await MacAPIClient.shared.fundPolicy()
            policy = loaded
            drafts = draft(from: loaded)
        } catch {
            loadFailed = true
        }
        loading = false
    }

    private func save() async {
        guard canEdit, dirty, !invalid else { return }
        saving = true
        error = nil
        saved = false
        defer { saving = false }
        var stages: [String: MacFundPolicy.Stage?] = [:]
        for stage in Self.stages {
            let d = drafts[stage] ?? Draft()
            var entry = MacFundPolicy.Stage()
            var any = false
            if case .some(.some(let v)) = number(d.moic) { entry.targetMoic = v; any = true }
            if case .some(.some(let v)) = number(d.irr) { entry.targetIrrPct = v; any = true }
            if case .some(.some(let v)) = number(d.hold) { entry.maxHoldYears = v; any = true }
            if case .some(.some(let v)) = number(d.position) { entry.maxPositionPct = v; any = true }
            entry.basis = d.basis
            stages[stage] = any ? entry : nil
        }
        do {
            let result = try await MacAPIClient.shared.updateFundPolicy(stages: stages)
            policy = result
            drafts = draft(from: result)
            saved = true
        } catch {
            self.error = "Could not save the policy: \(error.localizedDescription)"
        }
    }
}

// MARK: - What only the Mac has

/// The Mac's own settings, in the website's trays: its server, how it signs in, the desk it
/// syncs, the MCP connector and the thesis.
private struct MacBureauMacTrays: View {
    @EnvironmentObject private var store: MacAppStore
    @Environment(\.colorScheme) private var colorScheme
    @State private var serverURL = MacConfig.baseURL.absoluteString
    @State private var serviceToken = ""
    @State private var requireLogin = UserDefaults.standard.bool(forKey: MacConfig.bypassLoginKey)
    @State private var testResult: String?
    @State private var testing = false

    private var ink: MacBureauPageInk { MacBureauPageInk(scheme: colorScheme) }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            VStack(alignment: .leading, spacing: 0) {
                MacBureauTrayTitle(title: "This Mac", icon: "monitor")
                note("The server this app reads, how it signs in, and the desk it keeps in step with the website and iPad.")
                    .padding(.top, 4)

                MacBureauKicker("Server").padding(.top, 16).padding(.bottom, 8)
                HStack(spacing: 8) {
                    MacBureauField(placeholder: "http://127.0.0.1:8010", text: $serverURL, onSubmit: saveServer)
                    MacBureauButton("Save", size: .small, action: saveServer)
                    MacBureauButton("Test connection", size: .small, busy: testing) { Task { await testServer() } }
                        .disabled(testing)
                }
                if let testResult {
                    Text(testResult)
                        .font(BSHType.bureauSans(12))
                        .foregroundStyle(testResult.hasPrefix("Success") ? ink.successInk : ink.warningInk)
                        .padding(.top, 6)
                }

                MacBureauKicker("Authentication").padding(.top, 20).padding(.bottom, 4)
                HStack(spacing: 12) {
                    Text("Require sign-in in this app")
                        .font(BSHType.bureauSans(14))
                        .tracking(-0.084)
                        .foregroundStyle(ink.secondary)
                    Spacer(minLength: 0)
                    MacBureauSwitch(isOn: $requireLogin)
                }
                .padding(.horizontal, 4)
                .padding(.vertical, 8)
                .onChange(of: requireLogin) { _, value in
                    UserDefaults.standard.set(value, forKey: MacConfig.bypassLoginKey)
                    Task {
                        if value {
                            await store.refreshSession()
                            if store.session == nil || store.session?.isAnonDev == true { store.showLoginSheet = true }
                        } else {
                            await store.bootstrap()
                            if store.session != nil { store.showLoginSheet = false }
                        }
                    }
                }
                note("Hides the local dev identity behind the sign-in sheet. The server still accepts unauthenticated requests while BSH_ALLOW_ANON_DEV=1.")
                HStack(spacing: 8) {
                    MacBureauField(placeholder: "Service token (read-only, for tooling)", text: $serviceToken, secure: true)
                    MacBureauButton("Use token", size: .small) {
                        MacConfig.writeToken(serviceToken)
                        serviceToken = ""
                        Task { await store.bootstrap() }
                    }
                    .disabled(serviceToken.isEmpty)
                    MacBureauButton("Forget stored token", size: .small) {
                        MacConfig.clearToken()
                        Task { await store.signOut() }
                    }
                }
                .padding(.top, 10)
                note("Sessions are stored in the macOS Keychain. Sign in for a personal session; the service token is only for tooling.")
                    .padding(.top, 6)

                MacBureauKicker("Desk sync · web, iPad and Mac").padding(.top, 20).padding(.bottom, 8)
                VStack(spacing: 6) {
                    MacBureauRow(label: "Pinned watchlist tickers", value: "\(store.pinnedTickers.count) symbols")
                    MacBureauRow(label: "Portfolio book lots", value: "\(store.bookLots.count) positions")
                    MacBureauRow(label: "Price alert rules", value: "\(store.alertRules.filter(\.enabled).count) active of \(store.alertRules.count)")
                }
                HStack(spacing: 8) {
                    MacBureauButton("Sync now", icon: "refresh-cw", size: .small) {
                        Task {
                            await store.refreshDeskPrefs()
                            await store.refreshMarket()
                        }
                    }
                    MacBureauButton("Reload everything", size: .small) { Task { await store.bootstrap() } }
                }
                .padding(.top, 10)
            }
            .bureauTray()

            VStack(alignment: .leading, spacing: 0) {
                MacBureauTrayTitle(title: "MCP connector", icon: "plug")
                note("Expose the firm's memory — memos, decisions, calls, transcripts, portfolio, signal scores — to any MCP client. Read-only.")
                    .padding(.top, 4)
                Text("uv run python scripts/bsh_mcp.py")
                    .font(.system(size: 12, design: .monospaced))
                    .foregroundStyle(ink.ink)
                    .textSelection(.enabled)
                    .padding(.horizontal, 12)
                    .frame(maxWidth: .infinity, minHeight: 36, alignment: .leading)
                    .background(RoundedRectangle(cornerRadius: 11, style: .circular).fill(ink.fillTertiary))
                    .padding(.top, 12)
                MacBureauButton("Copy Claude Desktop config", icon: "copy", size: .small) {
                    let config = """
                    {"mcpServers": {"bsh-research": {"command": "uv", "args": ["run", "--directory", "/PATH/TO/bsh-research-center", "python", "scripts/bsh_mcp.py"]}}}
                    """
                    NSPasteboard.general.clearContents()
                    NSPasteboard.general.setString(config, forType: .string)
                }
                .padding(.top, 10)
            }
            .bureauTray()

            VStack(alignment: .leading, spacing: 12) {
                MacBureauTrayTitle(title: "Thesis", icon: "scale")
                MacThesisEditor()
            }
            .bureauTray()
        }
    }

    private func note(_ text: String) -> some View {
        Text(text)
            .font(BSHType.bureauSans(12))
            .foregroundStyle(ink.muted)
            .bureauLines(16, size: 12)
            .fixedSize(horizontal: false, vertical: true)
    }

    private func saveServer() {
        guard let url = MacConfig.normalizedBaseURL(serverURL) else {
            testResult = "Invalid base URL: include a host, e.g. http://192.168.1.5:8010"
            return
        }
        testResult = "Saved base URL: \(url.absoluteString)"
        Task {
            await store.switchServer(to: url.absoluteString)
            serverURL = MacConfig.baseURL.absoluteString
        }
    }

    private func testServer() async {
        testing = true
        testResult = nil
        defer { testing = false }
        guard let base = MacConfig.normalizedBaseURL(serverURL) else {
            testResult = "Connection failed: enter a full http(s) URL (current: \(MacConfig.baseURL.absoluteString))"
            return
        }
        let suffix = base.absoluteString == MacConfig.baseURL.absoluteString ? "" : " (not saved yet; current: \(MacConfig.baseURL.absoluteString))"
        var req = URLRequest(url: base.appendingPathComponent("api").appendingPathComponent("health"), timeoutInterval: 5)
        req.setValue("application/json", forHTTPHeaderField: "Accept")
        req.setValue("macos", forHTTPHeaderField: "X-BSH-Client")
        if let token = MacConfig.readToken() {
            req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        do {
            let (_, response) = try await URLSession.shared.data(for: req)
            switch (response as? HTTPURLResponse)?.statusCode ?? 0 {
            case 200..<300: testResult = "Success: \(base.absoluteString) is reachable\(suffix)"
            case 401: testResult = "Reachable, but \(base.absoluteString) requires sign-in\(suffix)"
            case let status: testResult = "Connection failed: HTTP \(status) from \(base.absoluteString)\(suffix)"
            }
        } catch {
            testResult = "Connection failed: \(error.localizedDescription)\(suffix)"
        }
    }
}
