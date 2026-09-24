//
//  BSHDesignPickers.swift
//  Shared by BSHResearch (iPhone, iPad) and BSHResearchMac.
//
//  The two choosers the apps offer, in Settings and in the welcome tour:
//
//  - `BSHDesignCards`: Summit Glass, Bureau and Folio, each as a card with a miniature
//    of its page, its name set in its own type, and a line about it.
//  - `BSHBureauDeskPicker`: Bureau's desk colors as swatches. It is only offered while
//    Bureau is the design; Onyx & White (white by day, black by night) shows as a
//    circle split between its two desks.
//

import SwiftUI

// MARK: - Bureau's desk

struct BSHBureauDeskPicker: View {
    @Binding var selection: BSHBureauDesk
    var title: (BSHBureauDesk) -> String = { $0.title }
    var size: CGFloat = 26

    var body: some View {
        HStack(spacing: 8) {
            ForEach(BSHBureauDesk.allCases) { desk in
                let chosen = desk == selection
                Button {
                    selection = desk
                } label: {
                    BSHDeskSwatch(desk: desk, size: size)
                        .padding(3)
                        .overlay {
                            Circle().strokeBorder(chosen ? BSHPalette.accent : .clear, lineWidth: 2)
                        }
                        .contentShape(Circle())
                }
                .buttonStyle(.plain)
                .help(title(desk))
                .accessibilityLabel(title(desk))
                .accessibilityAddTraits(chosen ? .isSelected : [])
            }
        }
        .accessibilityElement(children: .contain)
    }
}

/// One desk color: its daytime desk, or Onyx's white and black split on the diagonal.
struct BSHDeskSwatch: View {
    let desk: BSHBureauDesk
    var size: CGFloat = 26

    var body: some View {
        Group {
            if desk == .onyx {
                Circle().fill(LinearGradient(
                    stops: [.init(color: .white, location: 0.5), .init(color: .black, location: 0.5)],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                ))
            } else {
                Circle().fill(desk.swatch)
            }
        }
        .overlay { Circle().strokeBorder(Color.primary.opacity(0.2), lineWidth: 0.5) }
        .frame(width: size, height: size)
    }
}

// MARK: - The designs

struct BSHDesignCards: View {
    @Binding var selection: BSHDesign
    var title: (BSHDesign) -> String = { $0.title }
    var caption: (BSHDesign) -> String
    /// The order shown: the default first.
    static let order: [BSHDesign] = [.glass, .bureau, .folio]

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            ForEach(Self.order) { design in
                let chosen = design == selection
                Button {
                    selection = design
                } label: {
                    VStack(alignment: .leading, spacing: 6) {
                        BSHDesignMiniature(design: design)
                            .frame(height: 58)
                            .overlay {
                                RoundedRectangle(cornerRadius: 9, style: .continuous)
                                    .strokeBorder(chosen ? BSHPalette.accent : Color.primary.opacity(0.14), lineWidth: chosen ? 2 : 0.5)
                            }
                        Text(title(design))
                            .font(BSHType.heading(14, in: design))
                            .lineLimit(1)
                            .minimumScaleFactor(0.8)
                        Text(caption(design))
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                            .multilineTextAlignment(.leading)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityElement(children: .combine)
                .accessibilityLabel("\(title(design)). \(caption(design))")
                .accessibilityAddTraits(chosen ? .isSelected : [])
            }
        }
    }
}

/// A miniature of a design's page: its ground, a card or the sheet with two lines of
/// text, and its color for acting. Drawn from the design's own values, whichever design
/// is active, and in the current appearance.
struct BSHDesignMiniature: View {
    let design: BSHDesign

    var body: some View {
        switch design {
        case .glass:
            ZStack(alignment: .topLeading) {
                Self.glassCanvas
                page(fill: Self.glassCard, ink: .primary, accent: .blue, radius: 7)
                    .padding(8)
            }
            .clipShape(RoundedRectangle(cornerRadius: 9, style: .continuous))
        case .bureau:
            let tones = BSHBureauDesk.active.tones
            ZStack(alignment: .topLeading) {
                Color.bshTone(tones.frame.light, tones.frame.dark)
                page(
                    fill: .bshTone(tones.sheet.light, tones.sheet.dark),
                    ink: .bshTone(tones.ink.light, tones.ink.dark),
                    accent: .bshTone(BSHRGB(148, 112, 47), BSHRGB(176, 138, 66)),
                    radius: 6,
                    ruled: true
                )
                .shadow(color: .black.opacity(0.2), radius: 3, y: 1)
                .padding(EdgeInsets(top: 9, leading: 12, bottom: 0, trailing: 6))
            }
            .clipShape(RoundedRectangle(cornerRadius: 9, style: .continuous))
        case .folio:
            ZStack(alignment: .topLeading) {
                Color.bshTone(BSHRGB(244, 242, 237), BSHRGB(22, 21, 19))
                page(
                    fill: .bshTone(BSHRGB(251, 250, 247), BSHRGB(30, 29, 26)),
                    ink: .bshTone(BSHRGB(26, 25, 22), BSHRGB(238, 235, 227)),
                    accent: .bshTone(BSHRGB(38, 60, 212), BSHRGB(122, 138, 255)),
                    radius: 3,
                    ruled: true
                )
                .padding(8)
            }
            .clipShape(RoundedRectangle(cornerRadius: 9, style: .continuous))
        }
    }

    private func page(fill: Color, ink: Color, accent: Color, radius: CGFloat, ruled: Bool = false) -> some View {
        RoundedRectangle(cornerRadius: radius, style: .continuous)
            .fill(fill)
            .overlay {
                if ruled {
                    RoundedRectangle(cornerRadius: radius, style: .continuous)
                        .strokeBorder(ink.opacity(0.12), lineWidth: 0.5)
                }
            }
            .overlay(alignment: .topLeading) {
                VStack(alignment: .leading, spacing: 4) {
                    Capsule().fill(ink.opacity(0.8)).frame(width: 30, height: 4)
                    Capsule().fill(ink.opacity(0.25)).frame(width: 44, height: 3)
                    Capsule().fill(accent).frame(width: 18, height: 6)
                }
                .padding(7)
            }
    }

    private static var glassCanvas: Color {
        #if canImport(UIKit)
        Color(uiColor: .systemGroupedBackground)
        #else
        Color(nsColor: .windowBackgroundColor)
        #endif
    }

    private static var glassCard: Color {
        #if canImport(UIKit)
        Color(uiColor: .secondarySystemGroupedBackground)
        #else
        Color(nsColor: .controlBackgroundColor)
        #endif
    }
}
