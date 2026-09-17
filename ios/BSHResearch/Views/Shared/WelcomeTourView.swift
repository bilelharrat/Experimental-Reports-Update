import SwiftUI

// MARK: - Anchoring

/// Real controls publish their bounds under an id so the tour can point at
/// them. Nothing here draws: the chrome stays the chrome.
struct WelcomeTourAnchorKey: PreferenceKey {
    static var defaultValue: [String: Anchor<CGRect>] { [:] }
    static func reduce(value: inout [String: Anchor<CGRect>], nextValue: () -> [String: Anchor<CGRect>]) {
        value.merge(nextValue()) { _, new in new }
    }
}

extension View {
    /// Mark this view as something the welcome tour can spotlight.
    func welcomeTourAnchor(_ id: String) -> some View {
        anchorPreference(key: WelcomeTourAnchorKey.self, value: .bounds) { [id: $0] }
    }

    /// Hang the tour over the app, resolving anchors in this view's space.
    func welcomeTourOverlay() -> some View {
        overlayPreferenceValue(WelcomeTourAnchorKey.self) { anchors in
            GeometryReader { proxy in
                WelcomeTourOverlay(
                    spotlight: { id in anchors[id].map { proxy[$0] } },
                    container: proxy.size
                )
            }
            .ignoresSafeArea()
        }
    }
}

private extension View {
    /// Punch `mask` out of this view — the dim everywhere but the control.
    @ViewBuilder
    func cutOut<Mask: View>(@ViewBuilder _ mask: () -> Mask) -> some View {
        self.mask {
            Rectangle()
                .overlay { mask().blendMode(.destinationOut) }
                .compositingGroup()
        }
    }
}

// MARK: - Overlay

/// The guided walkthrough. The welcome card is Apple's "Welcome to" sheet;
/// every step after it moves the app to the desk it is describing, dims the
/// screen only lightly, and rings the real control it is talking about.
struct WelcomeTourOverlay: View {
    let spotlight: (String) -> CGRect?
    let container: CGSize

    @EnvironmentObject private var tour: WelcomeTourStore
    @EnvironmentObject private var language: LanguageStore
    @Environment(\.colorScheme) private var colorScheme
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    @State private var calloutSize: CGSize = .zero

    /// Light on purpose: the screen underneath is the thing being explained.
    private var dimOpacity: Double { colorScheme == .dark ? 0.26 : 0.16 }
    private var flatDimOpacity: Double { colorScheme == .dark ? 0.34 : 0.24 }

    private var page: WelcomeTourPage? { tour.current }
    private var isHero: Bool { page?.isHero ?? true }

    private var halo: CGRect? {
        guard let id = page?.anchor, !isHero, let rect = spotlight(id) else { return nil }
        guard rect.width > 0, rect.height > 0 else { return nil }
        return rect.insetBy(dx: -8, dy: -8)
    }

    var body: some View {
        if tour.isPresented {
            ZStack(alignment: .topLeading) {
                dim
                if let halo {
                    RoundedRectangle(cornerRadius: min(22, halo.height / 2), style: .continuous)
                        .strokeBorder(Color.accentColor, lineWidth: 2)
                        .frame(width: halo.width, height: halo.height)
                        .position(x: halo.midX, y: halo.midY)
                        .shadow(color: Color.accentColor.opacity(0.5), radius: 10)
                        .allowsHitTesting(false)
                }

                callout
                    .frame(width: calloutWidth)
                    .background {
                        GeometryReader { geo in
                            Color.clear.onAppear { calloutSize = geo.size }
                                .onChange(of: geo.size) { _, size in calloutSize = size }
                        }
                    }
                    .offset(x: calloutOrigin.x, y: calloutOrigin.y)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
            .animation(reduceMotion ? nil : .spring(response: 0.42, dampingFraction: 0.86), value: tour.stepIndex)
            .animation(reduceMotion ? nil : .easeInOut(duration: 0.28), value: halo?.origin.y)
            .transition(.opacity)
            .accessibilityIdentifier("welcome-tour")
        }
    }

    // MARK: Dim

    @ViewBuilder
    private var dim: some View {
        let base = Rectangle().fill(Color.black.opacity(halo == nil ? flatDimOpacity : dimOpacity))
        Group {
            if let halo {
                base.cutOut {
                    RoundedRectangle(cornerRadius: min(22, halo.height / 2), style: .continuous)
                        .frame(width: halo.width, height: halo.height)
                        .position(x: halo.midX, y: halo.midY)
                }
            } else {
                base
            }
        }
        .ignoresSafeArea()
        .contentShape(Rectangle())
        // Tapping the dim moves on, the way Apple's coach marks do.
        .onTapGesture { if !isHero { tour.advance() } }
        .accessibilityHidden(true)
    }

    // MARK: Callout

    private var calloutWidth: CGFloat {
        let maximum = container.width - 32
        return isHero ? min(420, maximum) : min(360, maximum)
    }

    /// Beside the control when there is one, centred when there isn't.
    private var calloutOrigin: CGPoint {
        let width = calloutWidth
        let height = calloutSize.height > 0 ? calloutSize.height : 260
        let margin: CGFloat = 16

        guard let halo else {
            return CGPoint(
                x: max(margin, (container.width - width) / 2),
                y: max(margin, (container.height - height) / 2)
            )
        }

        let x = min(max(margin, halo.midX - width / 2), max(margin, container.width - width - margin))
        let below = halo.maxY + 14
        let above = halo.minY - height - 14
        let y = below + height + margin <= container.height
            ? below
            : max(margin, above)
        return CGPoint(x: x, y: y)
    }

    private var callout: some View {
        VStack(alignment: .leading, spacing: 0) {
            if isHero {
                heroContent
            } else if let page {
                stepContent(page)
            }
            footer
        }
        .padding(isHero ? 22 : 16)
        .background {
            RoundedRectangle(cornerRadius: 22, style: .continuous)
                .fill(.regularMaterial)
                .overlay {
                    RoundedRectangle(cornerRadius: 22, style: .continuous)
                        .strokeBorder(Color.primary.opacity(0.08), lineWidth: 0.5)
                }
                .shadow(color: Color.black.opacity(0.28), radius: 24, y: 10)
        }
    }

    private var heroContent: some View {
        VStack(spacing: 0) {
            BSHBrandTile(size: 74, cornerRadius: 18)
                .padding(.bottom, 16)

            Text(language.t("welcome.title"))
                .font(.title.weight(.bold))
                .multilineTextAlignment(.center)
                .accessibilityIdentifier("welcome-tour-title")

            Text(language.t("welcome.subtitle"))
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .padding(.top, 6)

            VStack(alignment: .leading, spacing: 14) {
                ForEach(WelcomeTourCatalog.rows) { row in
                    HStack(alignment: .top, spacing: 12) {
                        rowIcon(row)
                        VStack(alignment: .leading, spacing: 1) {
                            Text(language.t(row.titleKey)).font(.subheadline.weight(.semibold))
                            Text(language.t(row.bodyKey))
                                .font(.footnote)
                                .foregroundStyle(.secondary)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                }
            }
            .padding(.top, 20)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    private func stepContent(_ page: WelcomeTourPage) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .top, spacing: 12) {
                glyph(page)
                VStack(alignment: .leading, spacing: 3) {
                    Text(language.t(page.titleKey))
                        .font(.headline)
                        .accessibilityIdentifier("welcome-tour-title")
                    Text(language.t(page.bodyKey))
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Spacer(minLength: 0)
            }

            if !page.tips.isEmpty {
                VStack(spacing: 6) {
                    ForEach(page.tips) { tip in
                        HStack(spacing: 10) {
                            Image(systemName: tip.symbol ?? "circle.fill")
                                .font(.system(size: 12, weight: .semibold))
                                .foregroundStyle(Color.accentColor)
                                .frame(width: 18)
                            Text(language.t(tip.textKey))
                                .font(.caption)
                                .fixedSize(horizontal: false, vertical: true)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }
                        .padding(.horizontal, 10)
                        .padding(.vertical, 8)
                        .background {
                            RoundedRectangle(cornerRadius: 10, style: .continuous)
                                .fill(Color.primary.opacity(colorScheme == .dark ? 0.08 : 0.05))
                        }
                    }
                }
            }
        }
    }

    private var footer: some View {
        VStack(spacing: 12) {
            HStack(spacing: 6) {
                ForEach(tour.pages.indices, id: \.self) { index in
                    Circle()
                        .fill(index == tour.stepIndex ? Color.accentColor : Color.primary.opacity(0.18))
                        .frame(width: 6, height: 6)
                }
            }
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(
                language.t("welcome.page_of")
                    .replacingOccurrences(of: "{current}", with: String(tour.stepIndex + 1))
                    .replacingOccurrences(of: "{total}", with: String(tour.pages.count))
            )

            HStack(spacing: 10) {
                if !tour.isFirstStep {
                    Button(language.t("welcome.back")) { tour.back() }
                        .font(.subheadline)
                        .buttonStyle(.plain)
                        .foregroundStyle(Color.accentColor)
                        .accessibilityIdentifier("welcome-tour-back")
                } else if !tour.isLastStep {
                    Button(language.t("welcome.close")) { tour.complete() }
                        .font(.subheadline)
                        .buttonStyle(.plain)
                        .foregroundStyle(.secondary)
                        .accessibilityIdentifier("welcome-tour-skip")
                }

                Spacer(minLength: 0)

                Button {
                    tour.advance()
                } label: {
                    Text(language.t(tour.isLastStep ? "welcome.get_started" : "welcome.continue"))
                        .font(.subheadline.weight(.semibold))
                        .padding(.horizontal, 14)
                        .padding(.vertical, 6)
                }
                .buttonStyle(.borderedProminent)
                .accessibilityIdentifier("welcome-tour-next")
            }

            if isHero {
                Text(language.t("welcome.replay_hint"))
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
                    .multilineTextAlignment(.center)
            }
        }
        .padding(.top, 16)
    }

    // MARK: Glyphs

    @ViewBuilder
    private func glyph(_ page: WelcomeTourPage) -> some View {
        if page.usesWarrenPortrait {
            Image(AskInvestor.buffett.imageName)
                .resizable()
                .scaledToFill()
                .frame(width: 40, height: 40)
                .clipShape(Circle())
                .accessibilityHidden(true)
        } else {
            Image(systemName: page.symbol ?? "sparkles")
                .font(.system(size: 17, weight: .semibold))
                .foregroundStyle(Color.accentColor)
                .frame(width: 40, height: 40)
                .background(
                    Color.accentColor.opacity(colorScheme == .dark ? 0.18 : 0.12),
                    in: RoundedRectangle(cornerRadius: 11, style: .continuous)
                )
                .accessibilityHidden(true)
        }
    }

    @ViewBuilder
    private func rowIcon(_ row: WelcomeTourRow) -> some View {
        if row.usesWarrenPortrait {
            Image(AskInvestor.buffett.imageName)
                .resizable()
                .scaledToFill()
                .frame(width: 34, height: 34)
                .clipShape(Circle())
                .accessibilityHidden(true)
        } else {
            Image(systemName: row.symbol ?? "circle")
                .font(.system(size: 16, weight: .semibold))
                .foregroundStyle(Color.accentColor)
                .frame(width: 34, height: 34)
                .background(
                    Color.accentColor.opacity(colorScheme == .dark ? 0.18 : 0.12),
                    in: RoundedRectangle(cornerRadius: 10, style: .continuous)
                )
                .accessibilityHidden(true)
        }
    }
}
