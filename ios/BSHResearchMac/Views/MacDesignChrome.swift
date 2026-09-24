//
//  MacDesignChrome.swift
//  BSHResearchMac
//
//  The window's shell in each design (BSHDesign). The desks themselves only use the
//  tokens and components in MacDesign.swift / MacGlassStyles.swift; these modifiers are
//  where the shell changes shape:
//
//  - Summit Glass: the Mac's own vibrant sidebar and toolbar, untouched.
//  - Folio: the sidebar is a paper index column ruled off from the page; the toolbar is
//    paper too. A chosen row is a bookmark (GlassRowHighlight).
//  - Bureau: the sidebar and the toolbar are the green desk, written in ivory; the desk
//    you are on is one ivory sheet laid on it with a gutter; the chosen row is a slip of
//    that sheet, so its label takes the page's ink.
//

import AppKit
import SwiftUI

/// The sidebar's list: its own material hidden on paper, so the ground below shows.
struct MacSidebarSurface: ViewModifier {
    /// The rule above the account footer.
    static var rule: Color {
        switch BSHDesign.active {
        case .bureau: return BSHPalette.bureauOnFrame.opacity(0.12)
        case .folio: return .dsHairline
        case .glass: return Color.primary.opacity(0.1)
        }
    }

    func body(content: Content) -> some View {
        if BSHDesign.active.isPaper {
            content.scrollContentBackground(.hidden)
        } else {
            content
        }
    }
}

/// What the sidebar column is drawn on, and the ink it is written in. Apply it outside
/// the column's `.toolbar` so the buttons over the sidebar take its appearance too.
struct MacSidebarGround: ViewModifier {
    @Environment(\.colorScheme) private var colorScheme

    func body(content: Content) -> some View {
        switch BSHDesign.active {
        case .glass:
            content
        case .folio:
            content
                .background(Color.dsCanvas)
                .overlay(alignment: .trailing) {
                    Rectangle().fill(Color.dsHairline).frame(width: 1)
                }
        case .bureau:
            content
                .foregroundStyle(BSHPalette.bureauOnFrame)
                .tint(BSHPalette.bureauBrass)
                .environment(\.bshOnFrame, true)
                .environment(\.bshPageScheme, colorScheme)
                // The desk is dark in either appearance, as the website's is: its
                // controls, and the toolbar buttons over it, draw light on the green.
                .environment(\.colorScheme, .dark)
                .background(BSHPalette.bureauFrame(for: colorScheme))
        }
    }
}

/// A sidebar row's label: under Bureau, the chosen row is a slip of the ivory sheet, so
/// its label is set in the page's ink rather than the desk's ivory.
struct MacSidebarRowInk: ViewModifier {
    var isSelected: Bool
    @Environment(\.bshPageScheme) private var pageScheme

    func body(content: Content) -> some View {
        if BSHDesign.active == .bureau && isSelected {
            content.foregroundStyle(pageScheme.map(BSHPalette.bureauInk(for:)) ?? BSHPalette.bureauInk)
        } else {
            content
        }
    }
}

/// The detail column: under Bureau, the desk on screen is one ivory sheet with rounded
/// corners, laid on the green with a gutter; the other designs fill the column.
struct MacDeskSheet: ViewModifier {
    func body(content: Content) -> some View {
        if BSHDesign.active == .bureau {
            content
                .background(BSHPalette.bureauSheet)
                .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
                .overlay(
                    RoundedRectangle(cornerRadius: 14, style: .continuous)
                        .strokeBorder(Color.black.opacity(0.18), lineWidth: 0.5)
                )
                .shadow(color: .black.opacity(0.35), radius: 14, y: 8)
                .padding(EdgeInsets(top: 0, leading: 6, bottom: 8, trailing: 8))
                .background(BSHPalette.bureauFrame)
        } else {
            content
        }
    }
}

/// The window's toolbar: Bureau's desk green with its title and controls in light ink,
/// Folio's paper, Summit's own material.
struct MacWindowChrome: ViewModifier {
    @Environment(\.colorScheme) private var colorScheme

    func body(content: Content) -> some View {
        switch BSHDesign.active {
        case .glass:
            content
                .background(MacTitlebarAppearance(appearance: nil))
        case .folio:
            content
                .toolbarBackground(Color.dsCanvas, for: .windowToolbar)
                .toolbarBackground(.visible, for: .windowToolbar)
                .background(MacTitlebarAppearance(appearance: nil))
        case .bureau:
            content
                // The desk's green as the page around it resolves it, fixed: the
                // titlebar below draws in the dark appearance, where the dynamic green
                // would resolve to night's and part from the sidebar in light mode.
                .toolbarBackground(BSHPalette.bureauFrame(for: colorScheme), for: .windowToolbar)
                .toolbarBackground(.visible, for: .windowToolbar)
                .toolbarColorScheme(.dark, for: .windowToolbar)
                .background(MacTitlebarAppearance(appearance: NSAppearance(named: .darkAqua)))
        }
    }
}

/// Draws the window's titlebar (its title, traffic lights and toolbar controls) in the
/// given appearance, or the window's own when nil. Bureau's toolbar is the green desk in
/// either appearance, and `toolbarColorScheme` doesn't reach a macOS window toolbar, so
/// in light mode its controls would be dark on dark without this.
private struct MacTitlebarAppearance: NSViewRepresentable {
    var appearance: NSAppearance?

    func makeNSView(context: Context) -> Probe {
        Probe(appearance: appearance)
    }

    func updateNSView(_ view: Probe, context: Context) {
        view.titlebarAppearance = appearance
        view.apply()
    }

    final class Probe: NSView {
        var titlebarAppearance: NSAppearance?

        init(appearance: NSAppearance?) {
            titlebarAppearance = appearance
            super.init(frame: .zero)
        }

        @available(*, unavailable)
        required init?(coder: NSCoder) { nil }

        override func viewDidMoveToWindow() {
            super.viewDidMoveToWindow()
            apply()
        }

        func apply() {
            // The close button sits in the titlebar; its container also holds the
            // toolbar sections over the sidebar and the detail.
            let titlebar = window?.standardWindowButton(.closeButton)?.superview
            (titlebar?.superview ?? titlebar)?.appearance = titlebarAppearance
        }
    }
}
