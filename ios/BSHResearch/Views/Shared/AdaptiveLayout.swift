import SwiftUI
import UIKit

/// Shared iPad / regular-width layout constants and modifiers.
enum AdaptiveLayout {
    /// Comfortable reading width for lists, forms, and article bodies.
    static let readableMaxWidth: CGFloat = 720
    /// Slightly wider for quote desks / charts that benefit from horizontal room.
    static let wideReadableMaxWidth: CGFloat = 980
    /// Phone chart height.
    static let chartCompactHeight: CGFloat = 250
    /// iPad / regular chart height — uses landscape width better.
    static let chartRegularHeight: CGFloat = 340
    /// Landscape root chrome: expanded icon+label column (matches web `lg:w-[260px]`).
    static let rootSidebarExpanded: CGFloat = 240
    /// Landscape root chrome: collapsed icon rail (matches web `lg:w-[56px]`).
    static let rootSidebarRail: CGFloat = 64
    /// Master column when News/Market use an embedded dual-pane (not nested split).
    static let embeddedMasterMin: CGFloat = 300
    static let embeddedMasterIdeal: CGFloat = 360
    /// Collapsed news/market master: chevron rail so the article can go full width.
    static let embeddedMasterRail: CGFloat = 44

    static var isPad: Bool {
        UIDevice.current.userInterfaceIdiom == .pad
    }

    /// Root chrome: landscape-shaped iPad window → sidebar; otherwise bottom tabs.
    ///
    /// Do **not** use `horizontalSizeClass == .regular` alone — portrait iPad is
    /// usually regular×regular and would incorrectly get a sidebar. Size-class
    /// `vertical == .compact` is also unreliable (full-screen landscape iPad is
    /// often still regular×regular). Prefer explicit window aspect; hard-reject
    /// portrait interface orientation so the rail never sticks after rotate.
    static func prefersRootSidebar(width: CGFloat, height: CGFloat) -> Bool {
        guard isPad else { return false }
        if NSClassFromString("XCTestCase") != nil, width > 1, height > 1 {
            return width > height
        }
        if let orient = foregroundInterfaceOrientation {
            if orient.isPortrait { return false }
            if orient.isLandscape {
                // Stage Manager / split: only sidebar when the window is wide.
                if width > 1, height > 1 {
                    return width > height
                }
                return true
            }
        }
        if width > 1, height > 1 {
            return width > height
        }
        return false
    }

    private static var foregroundInterfaceOrientation: UIInterfaceOrientation? {
        let scenes = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }
        return scenes.first(where: { $0.activationState == .foregroundActive })?.interfaceOrientation
            ?? scenes.first?.interfaceOrientation
    }
}

// MARK: - Root split embedding

private struct EmbeddedInRootSplitKey: EnvironmentKey {
    static let defaultValue = false
}

extension EnvironmentValues {
    /// True when this view is the detail of the landscape root sidebar chrome.
    /// Nested `NavigationSplitView`s must not be used here — they fight the
    /// root column layout and blank the detail.
    var embeddedInRootSplit: Bool {
        get { self[EmbeddedInRootSplitKey.self] }
        set { self[EmbeddedInRootSplitKey.self] = newValue }
    }
}

// MARK: - Readable width

private struct ReadableContentWidthModifier: ViewModifier {
    @Environment(\.horizontalSizeClass) private var sizeClass
    @Environment(\.embeddedInRootSplit) private var embeddedInRootSplit
    var maxWidth: CGFloat

    func body(content: Content) -> some View {
        // Landscape root sidebar detail must fill edge-to-edge (padding only).
        // Portrait / phone tabs force compact size class and skip the cap.
        if AdaptiveLayout.shouldConstrainReadableWidth(
            sizeClass: sizeClass,
            embeddedInRootSplit: embeddedInRootSplit
        ) {
            content
                .frame(maxWidth: maxWidth)
                .frame(maxWidth: .infinity)
        } else {
            content
        }
    }
}

extension AdaptiveLayout {
    /// Whether `readableContentWidth` should center+cap. False in MainSidebarChrome
    /// so Home/News/Pulse/Settings lists use the full detail pane width.
    static func shouldConstrainReadableWidth(
        sizeClass: UserInterfaceSizeClass?,
        embeddedInRootSplit: Bool
    ) -> Bool {
        sizeClass == .regular && !embeddedInRootSplit
    }
}

extension View {
    /// Center content and cap width on regular-width canvases that are *not*
    /// the landscape root sidebar detail (which must fill edge-to-edge).
    func readableContentWidth(_ maxWidth: CGFloat = AdaptiveLayout.readableMaxWidth) -> some View {
        modifier(ReadableContentWidthModifier(maxWidth: maxWidth))
    }

    /// Sheet chrome sized for iPad: large page sheet; phone keeps medium+large when requested.
    func bshSheetChrome(allowsMedium: Bool = false) -> some View {
        Group {
            if AdaptiveLayout.isPad || !allowsMedium {
                self.presentationDetents([.large])
            } else {
                self.presentationDetents([.medium, .large])
            }
        }
        .presentationDragIndicator(.visible)
        .presentationCornerRadius(AdaptiveLayout.isPad ? 20 : 28)
    }
}
