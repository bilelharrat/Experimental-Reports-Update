//
//  MacDesignChrome.swift
//  BSHResearchMac
//
//  The split view's shell in Summit Glass and Folio (BSHDesign). The desks themselves only
//  use the tokens and components in MacDesign.swift / MacGlassStyles.swift; these modifiers
//  are where the shell changes shape:
//
//  - Summit Glass: the Mac's own vibrant sidebar and toolbar, untouched.
//  - Folio: the sidebar is a paper index column ruled off from the page; the toolbar is
//    paper too. A chosen row is a bookmark (GlassRowHighlight).
//
//  Bureau doesn't use the split view: it draws the whole window as the website does
//  (MacBureauShell.swift).
//

import SwiftUI

/// The sidebar's list: its own material hidden on paper, so the ground below shows.
struct MacSidebarSurface: ViewModifier {
    /// The rule above the account footer.
    static var rule: Color {
        BSHDesign.active == .folio ? .dsHairline : Color.primary.opacity(0.1)
    }

    func body(content: Content) -> some View {
        if BSHDesign.active.isPaper {
            content.scrollContentBackground(.hidden)
        } else {
            content
        }
    }
}

/// What the sidebar column is drawn on: Folio's paper, ruled off from the page.
struct MacSidebarGround: ViewModifier {
    func body(content: Content) -> some View {
        if BSHDesign.active == .folio {
            content
                .background(Color.dsCanvas)
                .overlay(alignment: .trailing) {
                    Rectangle().fill(Color.dsHairline).frame(width: 1)
                }
        } else {
            content
        }
    }
}

/// The window's toolbar: Folio's paper, Summit's own material.
struct MacWindowChrome: ViewModifier {
    func body(content: Content) -> some View {
        if BSHDesign.active == .folio {
            content
                .toolbarBackground(Color.dsCanvas, for: .windowToolbar)
                .toolbarBackground(.visible, for: .windowToolbar)
        } else {
            content
        }
    }
}
